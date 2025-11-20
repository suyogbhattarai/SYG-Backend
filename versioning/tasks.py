# versioning/tasks.py

import os
import hashlib
import zipfile
import shutil
import fnmatch
from celery import shared_task
from django.conf import settings
from .models import PendingPush, Version
from django.utils import timezone
import json
import re


def compute_file_hash(file_path):
    """Compute SHA256 hash of a file"""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            sha256.update(chunk)
    return sha256.hexdigest()


def update_push_progress(push: PendingPush, status: str, progress: int, message: str = None):
    """Update push status and progress"""
    push.status = status
    push.progress = progress
    if message is not None:
        push.message = message
    push.save()


def get_next_version_number(project):
    """Get the next sequential version number"""
    last_version = project.versions.order_by('-id').first()
    if last_version and last_version.file:
        try:
            match = re.search(r'_v(\d+)\.zip', last_version.file.name)
            if match:
                return int(match.group(1)) + 1
        except Exception:
            pass
    return project.versions.count() + 1


def should_ignore_file(rel_path, ignore_patterns):
    """Check if file should be ignored based on patterns"""
    for pattern in ignore_patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        # Also check if any parent directory matches
        path_parts = rel_path.split('/')
        for i in range(len(path_parts)):
            partial_path = '/'.join(path_parts[:i+1])
            if fnmatch.fnmatch(partial_path, pattern):
                return True
    return False


@shared_task(bind=True)
def process_pending_push(self, push_id):
    """Process a pending push with user context and ignore patterns"""
    try:
        push = PendingPush.objects.select_related('project', 'created_by', 'version').get(id=push_id)
        project = push.project
        version_obj = push.version
        creator = push.created_by

        # Check if push needs approval
        if push.status == 'awaiting_approval':
            update_push_progress(push, 'awaiting_approval', 0, "Waiting for project owner approval")
            return "Push awaiting approval"

        # Normalize file_list
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
                update_push_progress(
                    push, 
                    'processing', 
                    5, 
                    f"Ignored {ignored_count} files based on patterns"
                )
        
        update_push_progress(push, 'processing', 10, "Starting push process...")

        # Define master directory for the user's project
        master_dir = os.path.join(
            settings.MEDIA_ROOT, 
            'projects_storage', 
            project.owner.username, 
            project.name
        )
        os.makedirs(master_dir, exist_ok=True)
        update_push_progress(push, 'processing', 15, "Using project master directory")

        total_files = len(file_list) or 1
        copied_count = 0
        skipped_count = 0

        # Copy only changed/new files
        for idx, f in enumerate(file_list, start=1):
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
                    print(f"Error copying file {local_path}: {str(e)}")

            progress_pct = 15 + int((idx / total_files) * 35)
            update_push_progress(
                push, 
                'processing', 
                progress_pct, 
                f"Processed {idx}/{total_files} files"
            )

        # Remove files not in incoming file_list
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
                        print(f"Error removing file {full_path}: {str(e)}")

        # Remove empty directories
        for root, dirs, files in os.walk(master_dir, topdown=False):
            for dir_name in dirs:
                dir_path = os.path.join(root, dir_name)
                try:
                    if not os.listdir(dir_path):
                        os.rmdir(dir_path)
                except Exception:
                    pass

        update_push_progress(
            push, 
            'comparing', 
            55, 
            f"Master updated: {copied_count} copied, {skipped_count} unchanged, {removed_count} removed"
        )

        # Create zip with proper version number
        new_version_number = get_next_version_number(project)
        zip_name = f"{project.name}_v{new_version_number}.zip"
        zip_storage_dir = os.path.join(
            settings.MEDIA_ROOT, 
            'projects', 
            project.owner.username,
            project.name
        )
        os.makedirs(zip_storage_dir, exist_ok=True)
        zip_full_path = os.path.join(zip_storage_dir, zip_name)

        update_push_progress(push, 'zipping', 60, "Creating zip archive...")
        
        with zipfile.ZipFile(zip_full_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(master_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, master_dir)
                    zipf.write(file_path, arcname)

        # Get file statistics
        file_size = os.path.getsize(zip_full_path)
        file_count = len(file_list)
        file_size_mb = round(file_size / (1024 * 1024), 2)
        
        update_push_progress(
            push, 
            'comparing', 
            75, 
            f"Archive created: {file_count} files ({file_size_mb} MB)"
        )

        # Compute hash
        version_hash = compute_file_hash(zip_full_path)

        # Check if identical version exists
        existing_version = Version.objects.filter(
            project=project, 
            hash=version_hash
        ).first()
        
        if existing_version:
            previous_placeholder = version_obj
            push.version = existing_version
            push.mark_completed()
            
            update_push_progress(
                push, 
                'done', 
                100, 
                "No changes detected; mapped to existing version."
            )
            
            try:
                os.remove(zip_full_path)
            except Exception:
                pass
            
            if previous_placeholder and previous_placeholder.id != existing_version.id:
                try:
                    previous_placeholder.delete()
                except Exception:
                    pass
            
            return "No changes detected, associated with existing version."

        # Save new version
        relative_storage_path = os.path.join(
            'projects', 
            project.owner.username,
            project.name, 
            zip_name
        )
        version_obj.file = relative_storage_path
        version_obj.hash = version_hash
        version_obj.created_at = timezone.now()
        version_obj.created_by = creator  # Set the creator
        
        if hasattr(version_obj, 'file_size'):
            version_obj.file_size = file_size
        if hasattr(version_obj, 'file_count'):
            version_obj.file_count = file_count
        
        version_obj.save()

        # Mark push as completed
        push.mark_completed()

        update_push_progress(
            push, 
            'done', 
            100, 
            f"Version v{new_version_number} created successfully ({file_size_mb} MB)"
        )
        
        return f"Version v{new_version_number} created by {creator.username}"

    except PendingPush.DoesNotExist:
        return "PendingPush not found"
    except Exception as e:
        try:
            push = PendingPush.objects.get(id=push_id)
            push.mark_failed(error_message=str(e))
        except Exception:
            pass
        
        print(f"Error in process_pending_push: {str(e)}")
        import traceback
        traceback.print_exc()
        return str(e)