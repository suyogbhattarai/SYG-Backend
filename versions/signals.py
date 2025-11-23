"""
projects/signals.py
Signal handlers for automatic project cleanup
"""

import os
import shutil
from django.db.models.signals import pre_delete, post_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Project


def get_project_storage_path(project):
    """Get storage path for a project using projectname+UID"""
    from versions.models import sanitize_filename
    username = sanitize_filename(project.owner.username)
    user_id = project.owner.id
    projectname = sanitize_filename(project.name)
    project_uid = project.uid
    return os.path.join(
        settings.MEDIA_ROOT,
        'users',
        f'{username}_{user_id}',
        'projects',
        f'{projectname}_{project_uid}'
    )


@receiver(pre_delete, sender=Project)
def project_pre_delete(sender, instance, **kwargs):
    """
    Clean up project-specific blobs before project deletion
    Log which blobs are deleted and which are kept
    """
    print(f"\n{'='*80}")
    print(f"[PROJECT CLEANUP] Starting cleanup for project: {instance.name} (UID: {instance.uid})")
    print(f"[PROJECT CLEANUP] Owner: {instance.owner.username if instance.owner else 'Unknown'}")
    print(f"{'='*80}\n")
    
    # Import here to avoid circular imports
    from versions.models import BlobReference, FileBlob
    
    # Get all blob references for this project
    blob_refs = BlobReference.objects.filter(project=instance).select_related('blob')
    
    if not blob_refs.exists():
        print(f"[PROJECT CLEANUP] No blob references found for this project\n")
        return
    
    # Track statistics
    total_blobs = blob_refs.count()
    blobs_to_delete = []
    blobs_to_keep = []
    total_size_freed = 0
    total_size_kept = 0
    
    print(f"[PROJECT CLEANUP] Found {total_blobs} blob references to process\n")
    
    # Check each blob
    for blob_ref in blob_refs:
        blob = blob_ref.blob
        
        # Check if blob is used by other projects
        other_project_refs = BlobReference.objects.filter(
            blob=blob
        ).exclude(project=instance)
        
        other_projects_count = other_project_refs.values('project').distinct().count()
        
        if other_projects_count > 0:
            # Blob is used by other projects - keep it
            other_projects = other_project_refs.select_related('project', 'project__owner').distinct('project')[:5]
            project_names = []
            for ref in other_projects:
                username = ref.project.owner.username if ref.project.owner else 'Unknown'
                user_id = ref.project.owner.id if ref.project.owner else 'N/A'
                project_name = ref.project.name
                project_uid = ref.project.uid[:8]
                project_names.append(f"{username}_{user_id}:{project_name}_{project_uid}")
            
            more_text = f" (+{other_projects_count - len(project_names)} more)" if other_projects_count > len(project_names) else ""
            
            blobs_to_keep.append({
                'hash': blob.hash,
                'size': blob.size,
                'ref_count': blob.ref_count,
                'other_projects': other_projects_count,
                'project_names': project_names
            })
            total_size_kept += blob.size
            
            print(f"[BLOB KEEP] Hash: {blob.hash[:16]}... | Size: {blob.get_size_mb()} MB | Refs: {blob.ref_count}")
            print(f"            Reason: Still used by {other_projects_count} other project(s)")
            print(f"            Projects: {', '.join(project_names)}{more_text}\n")
        else:
            # Blob is only used by this project - will be deleted
            blobs_to_delete.append({
                'hash': blob.hash,
                'size': blob.size,
                'ref_count': blob.ref_count
            })
            total_size_freed += blob.size
            
            print(f"[BLOB DELETE] Hash: {blob.hash[:16]}... | Size: {blob.get_size_mb()} MB | Refs: {blob.ref_count}")
            print(f"              Reason: Only used by this project\n")
    
    # Print summary
    print(f"\n{'='*80}")
    print(f"[PROJECT CLEANUP] BLOB CLEANUP SUMMARY")
    print(f"{'='*80}")
    print(f"Total blobs processed:  {total_blobs}")
    print(f"Blobs to DELETE:        {len(blobs_to_delete)} ({round(total_size_freed / (1024 * 1024), 2)} MB)")
    print(f"Blobs to KEEP:          {len(blobs_to_keep)} ({round(total_size_kept / (1024 * 1024), 2)} MB)")
    print(f"Total storage freed:    {round(total_size_freed / (1024 * 1024), 2)} MB")
    print(f"Total storage preserved: {round(total_size_kept / (1024 * 1024), 2)} MB")
    print(f"{'='*80}\n")


@receiver(post_delete, sender=Project)
def project_post_delete(sender, instance, **kwargs):
    """
    Clean up project directory after deletion
    This runs after all versions and blob references have been deleted
    """
    try:
        project_dir = get_project_storage_path(instance)
        
        if os.path.exists(project_dir):
            # Get directory size before deletion
            total_size = 0
            file_count = 0
            for root, dirs, files in os.walk(project_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        total_size += os.path.getsize(file_path)
                        file_count += 1
                    except:
                        pass
            
            print(f"\n[PROJECT CLEANUP] Deleting project directory: {project_dir}")
            print(f"[PROJECT CLEANUP] Directory contains: {file_count} files, {round(total_size / (1024 * 1024), 2)} MB")
            
            # Delete directory
            shutil.rmtree(project_dir, ignore_errors=True)
            print(f"[PROJECT CLEANUP] ✓ Project directory deleted successfully")
            
            # Try to cleanup empty parent directories
            try:
                projects_dir = os.path.dirname(project_dir)
                if os.path.exists(projects_dir) and not os.listdir(projects_dir):
                    os.rmdir(projects_dir)
                    print(f"[PROJECT CLEANUP] ✓ Removed empty projects directory")
                    
                    # Try to cleanup user directory if empty
                    user_dir = os.path.dirname(projects_dir)
                    if os.path.exists(user_dir) and not os.listdir(user_dir):
                        os.rmdir(user_dir)
                        print(f"[PROJECT CLEANUP] ✓ Removed empty user directory")
            except Exception as e:
                print(f"[PROJECT CLEANUP] Note: Could not remove parent directories: {e}")
            
            print(f"[PROJECT CLEANUP] ✓ Project cleanup completed\n")
        else:
            print(f"[PROJECT CLEANUP] Project directory not found (may not have been created): {project_dir}\n")
    
    except Exception as e:
        print(f"[PROJECT CLEANUP ERROR] Error during directory cleanup: {e}\n")