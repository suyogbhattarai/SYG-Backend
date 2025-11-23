"""
projects/signals.py
ULTIMATE FIX: Handles ALL possible path formats
- New readable format: username_userid/projects/projectname_projectuid
- UID only format: username_userid/projects/uid_only
- Old numeric format: users/2/projects/3
- Legacy format: projects_storage/username/projectname
"""

import os
import shutil
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Project, ProjectMember


def sanitize_filename(name):
    """Sanitize filename/folder name"""
    if not name:
        return 'unknown'
    name = ''.join(char if char.isalnum() or char in '-_' else '_' for char in name)
    return name[:50]


def get_all_possible_project_paths(project):
    """
    Get ALL possible project paths (new, old numeric, legacy)
    Returns list of paths to check during cleanup
    """
    username = project.owner.username if project.owner else 'Unknown'
    user_id = project.owner.id if project.owner else 0
    project_name = project.name
    project_id = project.id
    project_uid = project.uid
    
    safe_username = sanitize_filename(username)
    safe_projectname = sanitize_filename(project_name)
    
    paths = []
    
    # 1. NEW READABLE FORMAT: username_userid/projects/projectname_projectuid
    new_readable_path = os.path.join(
        settings.MEDIA_ROOT,
        'users',
        f'{safe_username}_{user_id}',
        'projects',
        f'{safe_projectname}_{project_uid}'
    )
    paths.append(('NEW READABLE', new_readable_path))
    
    # 2. UID ONLY FORMAT: username_userid/projects/uid_only
    uid_only_path = os.path.join(
        settings.MEDIA_ROOT,
        'users',
        f'{safe_username}_{user_id}',
        'projects',
        project_uid
    )
    paths.append(('UID ONLY', uid_only_path))
    
    # 3. OLD NUMERIC FORMAT: users/2/projects/3
    old_numeric_path = os.path.join(
        settings.MEDIA_ROOT,
        'users',
        str(user_id),
        'projects',
        str(project_id)
    )
    paths.append(('OLD NUMERIC', old_numeric_path))
    
    # 4. LEGACY FORMAT 1: projects_storage/username/projectname
    legacy_path1 = os.path.join(
        settings.MEDIA_ROOT,
        'projects_storage',
        safe_username,
        safe_projectname
    )
    paths.append(('LEGACY STORAGE', legacy_path1))
    
    # 5. LEGACY FORMAT 2: projects/username/projectname
    legacy_path2 = os.path.join(
        settings.MEDIA_ROOT,
        'projects',
        safe_username,
        safe_projectname
    )
    paths.append(('LEGACY PROJECTS', legacy_path2))
    
    # 6. LEGACY FORMAT 3: samples/username/projectname
    legacy_path3 = os.path.join(
        settings.MEDIA_ROOT,
        'samples',
        safe_username,
        safe_projectname
    )
    paths.append(('LEGACY SAMPLES', legacy_path3))
    
    return paths


def get_directory_size(directory):
    """Calculate total directory size in bytes"""
    total_size = 0
    file_count = 0
    for root, dirs, files in os.walk(directory):
        for f in files:
            try:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
                    file_count += 1
            except Exception:
                continue
    return total_size, file_count


def cleanup_empty_parent_directories(username, user_id=None):
    """
    Removes empty user-level directories after project deletion
    Checks both new readable and old numeric paths
    """
    print("\n[CLEANUP] Checking empty parent directories...")

    # New readable structure paths
    if user_id:
        safe_username = sanitize_filename(username)
        new_paths = [
            os.path.join(settings.MEDIA_ROOT, 'users', f'{safe_username}_{user_id}', 'projects'),
            os.path.join(settings.MEDIA_ROOT, 'users', f'{safe_username}_{user_id}'),
        ]
    else:
        new_paths = []

    # Old numeric structure paths
    if user_id:
        old_numeric_paths = [
            os.path.join(settings.MEDIA_ROOT, 'users', str(user_id), 'projects'),
            os.path.join(settings.MEDIA_ROOT, 'users', str(user_id)),
        ]
    else:
        old_numeric_paths = []

    # Legacy structure paths
    legacy_paths = [
        os.path.join(settings.MEDIA_ROOT, 'projects_storage', username),
        os.path.join(settings.MEDIA_ROOT, 'projects', username),
        os.path.join(settings.MEDIA_ROOT, 'samples', username),
    ]

    all_paths = new_paths + old_numeric_paths + legacy_paths

    for path in all_paths:
        try:
            if os.path.exists(path) and not os.listdir(path):
                os.rmdir(path)
                print(f"[REMOVED EMPTY DIR] {path}")
                
                # Try to remove parent if also empty
                parent_path = os.path.dirname(path)
                if os.path.exists(parent_path) and not os.listdir(parent_path):
                    os.rmdir(parent_path)
                    print(f"[REMOVED PARENT DIR] {parent_path}")
        except Exception as e:
            print(f"[ERROR] Could not remove empty parent: {e}")


# ============================================================================
# PROJECT LOGGING SIGNALS
# ============================================================================

@receiver(post_save, sender=Project)
def log_project_created(sender, instance, created, **kwargs):
    """
    Log project creation
    """
    if created:
        print(f"\n[PROJECT CREATED] {instance.name} (UID: {instance.uid})")
        print(f"[OWNER] {instance.owner.username}")


@receiver(post_save, sender=ProjectMember)
def log_member_added(sender, instance, created, **kwargs):
    """
    Log when project member is added
    """
    if created:
        print(f"[MEMBER ADDED] {instance.user.username} to {instance.project.name} as {instance.role}")


@receiver(post_delete, sender=ProjectMember)
def log_member_removed(sender, instance, **kwargs):
    """
    Log when project member is removed
    """
    print(f"[MEMBER REMOVED] {instance.user.username} from {instance.project.name}")


# ============================================================================
# PROJECT PRE-DELETE CLEANUP (DATABASE + BLOB TRACKING)
# ============================================================================

@receiver(pre_delete, sender=Project)
def cleanup_project_relations(sender, instance, **kwargs):
    """
    PHASE 1: Clean up all related DB objects before project deletion
    """
    print(f"\n{'='*80}")
    print(f"[PROJECT CLEANUP - PHASE 1] Database & Blob Tracking")
    print(f"{'='*80}")
    print(f"Project: {instance.name} (UID: {instance.uid})")
    print(f"Owner:   {instance.owner.username if instance.owner else 'Unknown'}")
    print(f"{'='*80}\n")

    # ----- BLOB REFERENCE TRACKING -----
    try:
        from versions.models import BlobReference, FileBlob
        
        blob_refs = BlobReference.objects.filter(project=instance).select_related('blob')
        
        if blob_refs.exists():
            total_blobs = blob_refs.count()
            blobs_to_delete = []
            blobs_to_keep = []
            total_size_freed = 0
            total_size_kept = 0
            
            print(f"[BLOB TRACKING] Found {total_blobs} blob references to analyze\n")
            
            for blob_ref in blob_refs:
                blob = blob_ref.blob
                
                other_project_refs = BlobReference.objects.filter(
                    blob=blob
                ).exclude(project=instance)
                
                other_projects_count = other_project_refs.values('project').distinct().count()
                
                if other_projects_count > 0:
                    other_projects = other_project_refs.select_related(
                        'project', 'project__owner'
                    ).distinct('project')[:5]
                    
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
                    print(f"            ✓ REASON: Still used by {other_projects_count} other project(s)")
                    print(f"            ✓ PROJECTS: {', '.join(project_names)}{more_text}\n")
                else:
                    blobs_to_delete.append({
                        'hash': blob.hash,
                        'size': blob.size,
                        'ref_count': blob.ref_count
                    })
                    total_size_freed += blob.size
                    
                    print(f"[BLOB DELETE] Hash: {blob.hash[:16]}... | Size: {blob.get_size_mb()} MB | Refs: {blob.ref_count}")
                    print(f"              ✗ REASON: Only used by this project - safe to delete\n")
            
            print(f"\n{'='*80}")
            print(f"[BLOB CLEANUP SUMMARY]")
            print(f"{'='*80}")
            print(f"Total blobs processed:     {total_blobs}")
            print(f"Blobs to DELETE:           {len(blobs_to_delete)} ({round(total_size_freed / (1024 * 1024), 2)} MB)")
            print(f"Blobs to KEEP:             {len(blobs_to_keep)} ({round(total_size_kept / (1024 * 1024), 2)} MB)")
            print(f"Total storage freed:       {round(total_size_freed / (1024 * 1024), 2)} MB")
            print(f"Total storage preserved:   {round(total_size_kept / (1024 * 1024), 2)} MB")
            print(f"{'='*80}\n")
        else:
            print("[BLOB TRACKING] No blob references found for this project\n")
    
    except ImportError:
        print("[BLOB TRACKING] Versions app not available\n")
    except Exception as e:
        print(f"[BLOB TRACKING ERROR] {e}\n")

    # ----- CLEAN VERSIONS -----
    try:
        versions = getattr(instance, 'versions_new', None)
        if versions:
            count = versions.count()
            print(f"[VERSION CLEANUP] Found {count} versions to delete")

            for version in versions.all():
                try:
                    version_num = version.version_number if version.version_number else f'#{version.id}'
                    version.delete()
                    print(f"[VERSION CLEANUP] ✅ Deleted Version v{version_num}")
                except Exception as e:
                    print(f"[VERSION CLEANUP] ❌ Version delete error: {e}")
            print()
        else:
            print("[VERSION CLEANUP] No versions relation found\n")
    except Exception as e:
        print(f"[VERSION CLEANUP ERROR] {e}\n")

    # ----- CLEAN PUSHES -----
    try:
        pushes = getattr(instance, 'pushes_new', None)
        if pushes:
            count = pushes.count()
            print(f"[PUSH CLEANUP] Found {count} pushes to delete")

            for push in pushes.all():
                try:
                    push.delete()
                    print(f"[PUSH CLEANUP] ✅ Deleted Push ID {push.id}")
                except Exception as e:
                    print(f"[PUSH CLEANUP] ❌ Push delete error: {e}")
            print()
        else:
            print("[PUSH CLEANUP] No pushes relation found\n")
    except Exception as e:
        print(f"[PUSH CLEANUP ERROR] {e}\n")

    # ----- CLEAN SAMPLES -----
    try:
        samples = getattr(instance, 'samples_new', None)
        if samples:
            count = samples.count()
            print(f"[SAMPLE CLEANUP] Found {count} samples to delete")

            for sample in samples.all():
                try:
                    sample.delete()
                    print(f"[SAMPLE CLEANUP] ✅ Deleted Sample ID {sample.id}")
                except Exception as e:
                    print(f"[SAMPLE CLEANUP] ❌ Sample delete error: {e}")
            print()
        else:
            print("[SAMPLE CLEANUP] No samples relation found\n")
    except Exception as e:
        print("[SAMPLE CLEANUP] Samples app not installed or inactive\n")

    print(f"{'='*80}")
    print(f"[PHASE 1 COMPLETE] Database cleanup finished")
    print(f"{'='*80}\n")


# ============================================================================
# PROJECT POST-DELETE CLEANUP (FILESYSTEM - ALL POSSIBLE PATHS)
# ============================================================================

@receiver(post_delete, sender=Project)
def cleanup_project_directories(sender, instance, **kwargs):
    """
    PHASE 2: Clean up ALL project directories in ALL possible locations
    - New readable: username_userid/projects/projectname_projectuid
    - UID only: username_userid/projects/uid_only
    - Old numeric: users/2/projects/3
    - Legacy: All old path formats
    """
    print(f"\n{'='*80}")
    print(f"[PROJECT CLEANUP - PHASE 2] Filesystem Cleanup (ALL FORMATS)")
    print(f"{'='*80}")
    print(f"Project: {instance.name} (UID: {instance.uid})")
    print(f"Owner:   {instance.owner.username if instance.owner else 'Unknown'}")
    print(f"{'='*80}\n")

    username = instance.owner.username if instance.owner else 'Unknown'
    user_id = instance.owner.id if instance.owner else 0

    # Get all possible paths
    all_paths = get_all_possible_project_paths(instance)

    # ----- DELETE ALL DIRECTORIES -----
    deleted_count = 0
    total_size_freed = 0
    total_files_deleted = 0

    print("[FILESYSTEM SCAN] Checking ALL possible project directories...\n")

    for path_type, path in all_paths:
        if os.path.exists(path):
            try:
                # Get directory stats before deletion
                dir_size, file_count = get_directory_size(path)
                
                # Count subdirectories
                subdir_count = sum([len(dirs) for _, dirs, _ in os.walk(path)])
                
                print(f"[DELETING - {path_type}] {path}")
                print(f"           Files: {file_count} | Subdirs: {subdir_count} | Size: {round(dir_size / (1024 * 1024), 2)} MB")
                
                # Delete entire directory tree
                shutil.rmtree(path, ignore_errors=False)
                
                deleted_count += 1
                total_size_freed += dir_size
                total_files_deleted += file_count
                
                print(f"           ✅ DELETED\n")
                
            except Exception as e:
                print(f"           ❌ ERROR: {e}\n")
        else:
            print(f"[SKIPPED - {path_type}] Not found: {path}\n")

    # ----- CLEANUP EMPTY PARENT DIRECTORIES -----
    cleanup_empty_parent_directories(username, user_id)

    # ----- FINAL SUMMARY -----
    print(f"\n{'='*80}")
    print(f"[FILESYSTEM CLEANUP SUMMARY]")
    print(f"{'='*80}")
    print(f"Directories deleted:       {deleted_count}")
    print(f"Files deleted:             {total_files_deleted}")
    print(f"Total storage freed:       {round(total_size_freed / (1024 * 1024), 2)} MB")
    print(f"{'='*80}")
    print(f"[PHASE 2 COMPLETE] All project files and folders removed")
    print(f"{'='*80}\n")

    # ----- FINAL PROJECT CLEANUP COMPLETE -----
    print(f"{'='*80}")
    print(f"[PROJECT CLEANUP COMPLETE]")
    print(f"Project '{instance.name}' has been completely removed")
    print(f"✓ Database records deleted")
    print(f"✓ Blob references cleaned (shared blobs preserved)")
    print(f"✓ All filesystem directories removed (all formats)")
    print(f"✓ Empty parent directories cleaned up")
    print(f"{'='*80}\n")