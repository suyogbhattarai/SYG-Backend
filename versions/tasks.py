"""
versions/tasks.py
Celery tasks for version processing with file-based manifest storage
COMPLETE FIXED VERSION - Solves hash, duplicate detection, file size issues
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
    
    # Sort by path for consistency
    file_hashes.sort(key=lambda x: x['path'])
    
    # Compute hash
    manifest_str = json.dumps(file_hashes, sort_keys=True)
    return hashlib.sha256(manifest_str.encode()).hexdigest()

def update_push_progress(push: PendingPush, status: str, progress: int, message: str = None):
    """Update push status and progress"""
    push.status = status
    push.progress = progress
    if message is not None:
        push.message = message
    push.save()
    logger.info(f"Push {push.id}: status={status}, progress={progress}%, message={message}")

def should_ignore_file(rel_path, ignore_patterns):
    """Check if file should be ignored based on patterns"""
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
    """Determine if snapshot should be created for version"""
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
    logger.info(f"Creating new blob: {file_hash[:16]}... ({round(file_size / 1024 / 1024, 2)} MB)")

    with open(file_path, 'rb') as f:
        file_content = f.read()

    blob = FileBlob(hash=file_hash, size=file_size, ref_count=0)
    blob.file.save(file_hash, ContentFile(file_content), save=True)
    return blob

def create_cas_manifest(file_list, master_dir):
    """
    Create CAS manifest
    Returns: (manifest_dict, total_size, cas_count, inline_count)
    """
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
                logger.info(f"CAS stored: {rel_path} -> blob {blob.id}")
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

    logger.info(f"Manifest created: {cas_count} CAS files, {inline_count} inline files, total_size={total_size} bytes")
    return manifest, total_size, cas_count, inline_count


def create_snapshot_zip(master_dir, version_obj):
    """
    Create a full ZIP snapshot of the master directory
    Returns: (zip_file_path, file_size, file_count)
    """
    import tempfile
    
    temp_zip = tempfile.NamedTemporaryFile(delete=False, suffix='.zip', prefix='snapshot_')
    temp_zip.close()
    
    logger.info(f"Creating snapshot ZIP: {temp_zip.name}")
    
    total_files = 0
    with zipfile.ZipFile(temp_zip.name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(master_dir):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, master_dir)
                zipf.write(file_path, arcname)
                total_files += 1
    
    file_size = os.path.getsize(temp_zip.name)
    logger.info(f"Snapshot ZIP created: {total_files} files, {round(file_size / 1024 / 1024, 2)} MB")
    
    return temp_zip.name, file_size, total_files


@shared_task(bind=True)
def process_pending_push_new(self, push_id):
    """
    Process a pending push with proper hash saving and duplicate detection
    """
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
                update_push_progress(push, 'processing', 5, f"Ignored {ignored_count} files based on patterns")

        push.refresh_from_db()
        if push.status == 'cancelled' and version_obj:
            version_obj.delete()
            return "Push was cancelled"

        update_push_progress(push, 'processing', 10, "Starting push process...")

        # Setup master directory
        master_dir = get_project_master_path(project.owner.username, project.name)
        os.makedirs(master_dir, exist_ok=True)
        logger.info(f"Using master directory: {master_dir}")
        update_push_progress(push, 'processing', 15, "Using project master directory")

        # Copy files from plugin cache
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
                    logger.error(f"Error copying file {local_path}: {e}")

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
                        logger.error(f"Error removing file {full_path}: {e}")

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

        # Check cancellation again
        push.refresh_from_db()
        if push.status == 'cancelled' and version_obj:
            version_obj.delete()
            return "Push was cancelled"

        # Determine version number and storage strategy
        completed_versions = Version.objects.filter(project=project, status='completed').exclude(id=version_obj.id if version_obj else None)
        new_version_number = completed_versions.count() + 1
        is_snapshot = should_create_snapshot(new_version_number)

        update_push_progress(push, 'processing', 65, f"Creating version {new_version_number} - {'Snapshot' if is_snapshot else 'CAS'} storage")

        # ALWAYS create manifest for duplicate detection
        update_push_progress(push, 'processing', 70, "Creating manifest for duplicate detection...")
        manifest, total_size, cas_count, inline_count = create_cas_manifest(file_list, master_dir)
        manifest_hash = compute_manifest_hash(manifest)
        logger.info(f"Manifest hash: {manifest_hash}, files={len(manifest['files'])}")

        # Check for duplicate version BEFORE creating snapshot
        existing_version = Version.objects.filter(
            project=project, 
            hash=manifest_hash, 
            status='completed'
        ).exclude(id=version_obj.id if version_obj else None).first()
        
        if existing_version:
            logger.info(f"Duplicate detected! Mapping to existing version {existing_version.id}")
            previous_placeholder = version_obj
            push.version = existing_version
            push.mark_completed()
            existing_version_number = existing_version.get_version_number()
            update_push_progress(push, 'done', 100, f"Identified same files and mapping to previous version v{existing_version_number}")
            if previous_placeholder and previous_placeholder.id != existing_version.id:
                try:
                    previous_placeholder.delete()
                    logger.info(f"Deleted placeholder version {previous_placeholder.id}")
                except Exception as e:
                    logger.error(f"Error deleting placeholder: {e}")
            return f"No changes detected - mapped to v{existing_version_number}"

        # CRITICAL FIX: Update version object with hash and basic info
        version_obj.is_snapshot = is_snapshot
        version_obj.hash = manifest_hash  # SAVE THE HASH!
        version_obj.file_count = len(file_list)
        version_obj.file_size = total_size  # SAVE FILE SIZE!
        version_obj.created_at = timezone.now()
        version_obj.created_by = creator

        if is_snapshot:
            # Create full ZIP snapshot
            update_push_progress(push, 'processing', 75, f"Creating full ZIP snapshot for v{new_version_number}...")
            
            try:
                temp_zip_path, zip_size, zip_file_count = create_snapshot_zip(master_dir, version_obj)
                
                # Save ZIP to version
                with open(temp_zip_path, 'rb') as f:
                    version_obj.file.save(f'snapshot.zip', File(f), save=False)
                
                version_obj.file_size = zip_size
                version_obj.manifest_file_path = None
                version_obj.save()  # Save all fields including hash and file_size
                
                # Clean up temp file
                os.remove(temp_zip_path)
                
                update_push_progress(push, 'processing', 90, f"Snapshot v{new_version_number} created ({round(zip_size / 1024 / 1024, 2)} MB)")
                
            except Exception as e:
                logger.error(f"Error creating snapshot: {e}")
                raise
        else:
            # Save CAS manifest to file
            update_push_progress(push, 'processing', 80, "Saving CAS manifest...")
            version_obj.file = None
            version_obj.save()  # Save first with hash and file_size
            version_obj.save_manifest_to_file(manifest)

        # Mark version as completed
        version_obj.mark_completed()

        total_size_mb = round((version_obj.file_size or total_size) / (1024 * 1024), 2)
        storage_label = 'Snapshot' if is_snapshot else 'CAS'

        if is_snapshot:
            message = f"{storage_label} v{new_version_number} created ({total_size_mb} MB)"
        else:
            message = f"{storage_label} v{new_version_number} created ({total_size_mb} MB, {cas_count} CAS, {inline_count} inline)"

        update_push_progress(push, 'done', 100, message)
        push.mark_completed()

        logger.info(f"✓ Version v{new_version_number} completed successfully with hash {manifest_hash[:16]}...")
        return f"Version v{new_version_number} created by {creator.username}"

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
        logger.error(f"Error in process_pending_push_new: {str(e)}", exc_info=True)
        return str(e)