"""
versions/tasks.py
FIXED: Detailed file change tracking with filenames
"""

import os
import hashlib
import shutil
import fnmatch
import base64
import json
import zipfile
import logging
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from django.core.files.base import ContentFile
from django.core.files import File
from .models import (
    PendingPush, 
    Version, 
    FileBlob,
    get_project_master_path,
    get_version_storage_path
)

logger = logging.getLogger(__name__)

CAS_SIZE_THRESHOLD = 1 * 1024 * 1024
SNAPSHOT_INTERVAL = 10

def compute_file_hash(file_path):
    """Compute SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest()

def compute_manifest_hash(manifest):
    """Compute hash of manifest for duplicate detection"""
    files = manifest.get('files', [])
    file_hashes = []
    
    for f in files:
        file_hashes.append({
            'path': f.get('path'),
            'hash': f.get('hash'),
            'size': f.get('size')
        })
    
    file_hashes.sort(key=lambda x: x['path'])
    manifest_str = json.dumps(file_hashes, sort_keys=True)
    return hashlib.sha256(manifest_str.encode()).hexdigest()

def compare_with_previous_version(current_manifest, previous_version):
    """
    Compare with previous version and return detailed changes
    Returns: (files_added, files_modified, files_deleted, size_change, change_details)
    """
    if not previous_version:
        current_files = current_manifest.get('files', [])
        total_size = sum(f.get('size', 0) for f in current_files)
        
        added_files = [
            {
                'path': f['path'],
                'size': f.get('size', 0),
                'hash': f.get('hash')
            }
            for f in current_files
        ]
        
        change_details = {
            'added_files': added_files,
            'modified_files': [],
            'deleted_files': []
        }
        
        return len(current_files), 0, 0, total_size, change_details
    
    prev_manifest = previous_version.load_manifest_from_file()
    if not prev_manifest:
        current_files = current_manifest.get('files', [])
        total_size = sum(f.get('size', 0) for f in current_files)
        
        added_files = [
            {
                'path': f['path'],
                'size': f.get('size', 0),
                'hash': f.get('hash')
            }
            for f in current_files
        ]
        
        change_details = {
            'added_files': added_files,
            'modified_files': [],
            'deleted_files': []
        }
        
        return len(current_files), 0, 0, total_size, change_details
    
    current_files = {f['path']: f for f in current_manifest.get('files', [])}
    prev_files = {f['path']: f for f in prev_manifest.get('files', [])}
    
    files_added = 0
    files_modified = 0
    files_deleted = 0
    size_change = 0
    
    added_files = []
    modified_files = []
    deleted_files = []
    
    # Check for added and modified files
    for path, current_file in current_files.items():
        if path not in prev_files:
            files_added += 1
            size_change += current_file.get('size', 0)
            added_files.append({
                'path': path,
                'size': current_file.get('size', 0),
                'hash': current_file.get('hash')
            })
        else:
            prev_file = prev_files[path]
            if current_file.get('hash') != prev_file.get('hash'):
                files_modified += 1
                size_change += current_file.get('size', 0) - prev_file.get('size', 0)
                modified_files.append({
                    'path': path,
                    'old_size': prev_file.get('size', 0),
                    'new_size': current_file.get('size', 0),
                    'size_change': current_file.get('size', 0) - prev_file.get('size', 0),
                    'old_hash': prev_file.get('hash'),
                    'new_hash': current_file.get('hash')
                })
    
    # Check for deleted files
    for path, prev_file in prev_files.items():
        if path not in current_files:
            files_deleted += 1
            size_change -= prev_file.get('size', 0)
            deleted_files.append({
                'path': path,
                'size': prev_file.get('size', 0),
                'hash': prev_file.get('hash')
            })
    
    change_details = {
        'added_files': added_files,
        'modified_files': modified_files,
        'deleted_files': deleted_files
    }
    
    logger.info(f"Changes: +{files_added} added, ~{files_modified} modified, -{files_deleted} deleted")
    
    return files_added, files_modified, files_deleted, size_change, change_details

def update_push_progress(push: PendingPush, status: str, progress: int, message: str = None):
    """Update push status and progress"""
    push.status = status
    push.progress = progress
    if message is not None:
        push.message = message
    push.save()
    logger.info(f"Push {push.uid}: {status}, {progress}%, {message}")

def should_ignore_file(rel_path, ignore_patterns):
    """Check if file should be ignored"""
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        path_parts = rel_path.split('/')
        for i in range(len(path_parts)):
            partial_path = '/'.join(path_parts[:i+1])
            if fnmatch.fnmatch(partial_path, pattern):
                return True
    return False

def should_create_snapshot(version_number):
    """Determine if snapshot should be created"""
    return version_number % SNAPSHOT_INTERVAL == 0

def get_or_create_blob(file_path, file_hash):
    """Get or create blob for file"""
    try:
        blob = FileBlob.objects.get(hash=file_hash)
        logger.info(f"Using existing blob: {file_hash[:16]}...")
        return blob
    except FileBlob.DoesNotExist:
        pass

    file_size = os.path.getsize(file_path)
    logger.info(f"Creating blob: {file_hash[:16]}... ({round(file_size / 1024 / 1024, 2)} MB)")

    with open(file_path, 'rb') as f:
        file_content = f.read()

    blob = FileBlob(hash=file_hash, size=file_size, ref_count=0)
    blob.file.save(file_hash, ContentFile(file_content), save=True)
    return blob

def create_cas_manifest(file_list, master_dir):
    """Create CAS manifest"""
    manifest = {
        'files': [],
        'created_at': timezone.now().isoformat(),
        'cas_threshold_mb': CAS_SIZE_THRESHOLD / (1024 * 1024)
    }

    total_size = 0
    cas_count = 0
    inline_count = 0

    for file_entry in file_list:
        rel_path = file_entry.get('relative_path')
        file_hash = file_entry.get('hash')
        if not rel_path:
            continue

        file_path = os.path.join(master_dir, rel_path)
        if not os.path.exists(file_path):
            logger.warning(f"File not found: {file_path}")
            continue

        file_size = os.path.getsize(file_path)
        total_size += file_size

        manifest_entry = {
            'path': rel_path,
            'hash': file_hash,
            'size': file_size
        }

        if file_size > CAS_SIZE_THRESHOLD:
            try:
                blob = get_or_create_blob(file_path, file_hash)
                blob.increment_ref()
                manifest_entry['storage'] = 'cas'
                manifest_entry['blob_id'] = blob.id
                manifest_entry['blob_hash'] = blob.hash
                cas_count += 1
            except Exception as e:
                logger.error(f"Error storing blob for {rel_path}: {e}")
                with open(file_path, 'rb') as f:
                    file_content = base64.b64encode(f.read()).decode('utf-8')
                manifest_entry['storage'] = 'inline'
                manifest_entry['content'] = file_content
                inline_count += 1
        else:
            with open(file_path, 'rb') as f:
                file_content = base64.b64encode(f.read()).decode('utf-8')
            manifest_entry['storage'] = 'inline'
            manifest_entry['content'] = file_content
            inline_count += 1

        manifest['files'].append(manifest_entry)

    logger.info(f"Manifest: {cas_count} CAS, {inline_count} inline, total={total_size}")
    return manifest, total_size, cas_count, inline_count

def create_snapshot_zip(master_dir, version_obj):
    """Create snapshot ZIP"""
    import tempfile
    
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip', prefix='snapshot_')
    temp_zip.close()
    
    logger.info(f"Creating snapshot: {temp_zip.name}")
    
    total_files = 0
    with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(master_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, master_dir)
                zipf.write(file_path, arcname)
                total_files += 1
    
    file_size = os.path.getsize(temp_zip.name)
    logger.info(f"Snapshot created: {total_files} files, {round(file_size / 1024 / 1024, 2)} MB")
    
    return temp_zip.name, file_size, total_files

@shared_task(bind=True)
def process_pending_push_new(self, push_id):
    """Process pending push with detailed change tracking"""
    try:
        push = PendingPush.objects.select_related('project', 'created_by', 'version').get(id=push_id)
        project = push.project
        version_obj = push.version
        creator = push.created_by

        push.refresh_from_db()
        if push.status == 'cancelled':
            return "Push was cancelled"

        if push.status == 'awaiting_approval':
            update_push_progress(push, 'awaiting_approval', 0, "Waiting for approval")
            return "Push awaiting approval"

        if version_obj:
            version_obj.status = 'processing'
            version_obj.save(update_fields=['status'])

        # Normalize file list
        file_list = push.file_list or []
        normalized_file_list = []
        for f in file_list:
            if isinstance(f, str):
                try:
                    f = json.loads(f)
                except Exception:
                    continue
            if isinstance(f, dict):
                normalized_file_list.append(f)
        file_list = normalized_file_list

        # Apply ignore patterns
        ignore_patterns = project.ignore_patterns or []
        if ignore_patterns:
            filtered_list = []
            ignored_count = 0
            for f in file_list:
                rel_path = f.get('relative_path')
                if rel_path and should_ignore_file(rel_path, ignore_patterns):
                    ignored_count += 1
                    continue
                filtered_list.append(f)
            file_list = filtered_list
            if ignored_count > 0:
                update_push_progress(push, 'processing', 5, f"Ignored {ignored_count} files")

        push.refresh_from_db()
        if push.status == 'cancelled' and version_obj:
            version_obj.delete()
            return "Push was cancelled"

        update_push_progress(push, 'processing', 10, "Starting push process...")

        # Setup master directory
        master_dir = get_project_master_path(project.owner.username, project.name)
        os.makedirs(master_dir, exist_ok=True)
        update_push_progress(push, 'processing', 15, "Using project master directory")

        # Copy files
        total_files = len(file_list) or 1
        copied_count = 0
        skipped_count = 0

        for idx, f in enumerate(file_list, start=1):
            if idx % 10 == 0:
                push.refresh_from_db()
                if push.status == 'cancelled' and version_obj:
                    version_obj.delete()
                    return "Push was cancelled"

            local_path = f.get('local_path')
            rel_path = f.get('relative_path')
            expected_hash = f.get('hash')

            if not rel_path:
                continue

            dest_path = os.path.join(master_dir, rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)

            use_existing = False
            if os.path.exists(dest_path):
                try:
                    current_hash = compute_file_hash(dest_path)
                    if expected_hash and current_hash == expected_hash:
                        use_existing = True
                        skipped_count += 1
                except Exception:
                    pass

            if not use_existing and local_path and os.path.exists(local_path):
                try:
                    shutil.copy2(local_path, dest_path)
                    copied_count += 1
                except Exception as e:
                    logger.error(f"Error copying {local_path}: {e}")

            progress_pct = 15 + int((idx / total_files) * 40)
            update_push_progress(push, 'processing', progress_pct, f"Processed {idx}/{total_files} files")

        # Remove deleted files
        push.refresh_from_db()
        if push.status == 'cancelled' and version_obj:
            version_obj.delete()
            return "Push was cancelled"

        incoming_set = set([f.get('relative_path') for f in file_list if f.get('relative_path')])
        removed_count = 0
        for root, dirs, files in os.walk(master_dir):
            for fname in files:
                full_path = os.path.join(root, fname)
                rel = os.path.relpath(full_path, master_dir).replace('\\', '/')
                if rel not in incoming_set:
                    try:
                        os.remove(full_path)
                        removed_count += 1
                    except Exception as e:
                        logger.error(f"Error removing {full_path}: {e}")

        # Cleanup empty directories
        for root, dirs, files in os.walk(master_dir, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    pass

        update_push_progress(push, 'processing', 60, f"Master updated: {copied_count} copied, {skipped_count} unchanged, {removed_count} removed")

        push.refresh_from_db()
        if push.status == 'cancelled' and version_obj:
            version_obj.delete()
            return "Push was cancelled"

        # Get previous version
        previous_version = Version.objects.filter(
            project=project, 
            status='completed'
        ).exclude(uid=version_obj.uid if version_obj else None).order_by('-created_at').first()

        # Determine version number
        completed_versions = Version.objects.filter(
            project=project, 
            status='completed'
        ).exclude(uid=version_obj.uid if version_obj else None)
        new_version_number = completed_versions.count() + 1
        is_snapshot = should_create_snapshot(new_version_number)

        update_push_progress(push, 'processing', 65, f"Creating v{new_version_number} - {'Snapshot' if is_snapshot else 'CAS'}")

        # Create manifest
        update_push_progress(push, 'processing', 70, "Creating manifest...")
        manifest, total_size, cas_count, inline_count = create_cas_manifest(file_list, master_dir)
        manifest_hash = compute_manifest_hash(manifest)

        # Check for duplicate
        existing_version = Version.objects.filter(
            project=project, 
            hash=manifest_hash, 
            status='completed'
        ).exclude(uid=version_obj.uid if version_obj else None).first()
        
        if existing_version:
            logger.info(f"Duplicate detected! Mapping to v{existing_version.version_number}")
            previous_placeholder = version_obj
            push.version = existing_version
            push.mark_completed()
            update_push_progress(push, 'done', 100, f"Mapped to existing v{existing_version.version_number}")
            if previous_placeholder and previous_placeholder.uid != existing_version.uid:
                try:
                    previous_placeholder.delete()
                except Exception as e:
                    logger.error(f"Error deleting placeholder: {e}")
            return f"Mapped to v{existing_version.version_number}"

        # Calculate detailed changes
        files_added, files_modified, files_deleted, size_change, change_details = compare_with_previous_version(manifest, previous_version)

        # Update version
        version_obj.is_snapshot = is_snapshot
        version_obj.hash = manifest_hash
        version_obj.file_count = len(file_list)
        version_obj.file_size = total_size
        version_obj.created_at = timezone.now()
        version_obj.created_by = creator
        version_obj.previous_version = previous_version
        version_obj.files_added = files_added
        version_obj.files_modified = files_modified
        version_obj.files_deleted = files_deleted
        version_obj.size_change = size_change
        version_obj.change_details = change_details
        version_obj.version_number = new_version_number

        if is_snapshot:
            update_push_progress(push, 'processing', 75, f"Creating snapshot for v{new_version_number}...")
            
            try:
                temp_zip_path, zip_size, zip_file_count = create_snapshot_zip(master_dir, version_obj)
                
                with open(temp_zip_path, 'rb') as f:
                    version_obj.file.save(f'snapshot.zip', File(f), save=False)
                
                version_obj.file_size = zip_size
                version_obj.manifest_file_path = None
                version_obj.save()
                
                os.remove(temp_zip_path)
                
                update_push_progress(push, 'processing', 90, f"Snapshot v{new_version_number} created")
                
            except Exception as e:
                logger.error(f"Snapshot creation failed: {e}")
                raise
        else:
            update_push_progress(push, 'processing', 80, "Saving CAS manifest...")
            version_obj.file = None
            version_obj.save()
            version_obj.save_manifest_to_file(manifest)

        # Mark completed
        version_obj.mark_completed()

        total_size_mb = round((version_obj.file_size or total_size) / (1024 * 1024), 2)
        storage_label = 'Snapshot' if is_snapshot else 'CAS'

        # Build message with changes
        change_msg = f"+{files_added}" if files_added > 0 else ""
        if files_modified > 0:
            change_msg += f", ~{files_modified}" if change_msg else f"~{files_modified}"
        if files_deleted > 0:
            change_msg += f", -{files_deleted}" if change_msg else f"-{files_deleted}"
        
        if not change_msg:
            change_msg = "no changes"

        if is_snapshot:
            message = f"{storage_label} v{new_version_number} created ({total_size_mb} MB, {change_msg})"
        else:
            message = f"{storage_label} v{new_version_number} created ({total_size_mb} MB, {cas_count} CAS, {inline_count} inline, {change_msg})"

        update_push_progress(push, 'done', 100, message)
        push.mark_completed()

        logger.info(f"✓ Version v{new_version_number} completed")
        return f"Version v{new_version_number} created"

    except PendingPush.DoesNotExist:
        return "PendingPush not found"
    except Exception as e:
        try:
            push = PendingPush.objects.get(id=push_id)
            push.mark_failed(error_message=str(e))
            if push.version:
                try:
                    push.version.mark_failed()
                except Exception:
                    pass
        except Exception:
            pass
        logger.error(f"Error: {str(e)}", exc_info=True)
        return str(e)