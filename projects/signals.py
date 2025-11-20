# projects/signals.py
"""
Signal handlers for projects app
Includes comprehensive cleanup on project deletion
Handles database + filesystem cleanup safely
"""

import os
import shutil
from django.db.models.signals import post_save, post_delete, pre_delete
from django.dispatch import receiver
from django.conf import settings
from .models import Project, ProjectMember


# ============================================================================
# PROJECT LOGGING SIGNALS
# ============================================================================

@receiver(post_save, sender=Project)
def log_project_created(sender, instance, created, **kwargs):
    """
    Log project creation
    Reserved for future ActivityLog implementation
    """
    if created:
        pass


@receiver(post_save, sender=ProjectMember)
def log_member_added(sender, instance, created, **kwargs):
    """
    Log when project member is added
    """
    if created:
        pass


@receiver(post_delete, sender=ProjectMember)
def log_member_removed(sender, instance, **kwargs):
    """
    Log when project member is removed
    """
    pass


# ============================================================================
# PROJECT PRE-DELETE CLEANUP (DATABASE)
# ============================================================================

@receiver(pre_delete, sender=Project)
def cleanup_project_relations(sender, instance, **kwargs):
    """
    Clean up all related DB objects before project deletion
    Ensures Version and Push signals trigger properly
    """

    print(f"\n{'='*80}")
    print(f"[PROJECT CLEANUP] Preparing deletion for project: {instance.name}")
    print(f"[OWNER] {instance.owner.username}")
    print(f"{'='*80}")

    # ----- CLEAN VERSIONS -----
    try:
        versions = getattr(instance, 'versions_new', None)
        if versions:
            count = versions.count()
            print(f"[CLEANUP] Found {count} versions")

            for version in versions.all():
                try:
                    version.delete()
                    print(f"[CLEANUP] ✅ Deleted Version ID {version.id}")
                except Exception as e:
                    print(f"[CLEANUP] ❌ Version delete error: {e}")
        else:
            print("[CLEANUP] No versions relation found")
    except Exception as e:
        print(f"[ERROR] Version cleanup failed: {e}")

    # ----- CLEAN PUSHES -----
    try:
        pushes = getattr(instance, 'pushes_new', None)
        if pushes:
            count = pushes.count()
            print(f"[CLEANUP] Found {count} pushes")

            for push in pushes.all():
                try:
                    push.delete()
                    print(f"[CLEANUP] ✅ Deleted Push ID {push.id}")
                except Exception as e:
                    print(f"[CLEANUP] ❌ Push delete error: {e}")
        else:
            print("[CLEANUP] No pushes relation found")
    except Exception as e:
        print(f"[ERROR] Push cleanup failed: {e}")

    # ----- CLEAN SAMPLES -----
    try:
        samples = getattr(instance, 'samples_new', None)
        if samples:
            count = samples.count()
            print(f"[CLEANUP] Found {count} samples")

            for sample in samples.all():
                try:
                    sample.delete()
                    print(f"[CLEANUP] ✅ Deleted Sample ID {sample.id}")
                except Exception as e:
                    print(f"[CLEANUP] ❌ Sample delete error: {e}")
        else:
            print("[CLEANUP] No samples relation found")
    except Exception as e:
        print("[INFO] Samples app not installed or inactive")

    print(f"[DATABASE CLEANUP] Completed for {instance.name}")


# ============================================================================
# PROJECT POST DELETE CLEANUP (FILESYSTEM)
# ============================================================================

@receiver(post_delete, sender=Project)
def cleanup_project_directories(sender, instance, **kwargs):
    """
    Clean up all project directories AFTER project deletion
    """
    from versions.models import get_project_storage_path

    print(f"\n[FILESYSTEM CLEANUP] Starting cleanup for: {instance.name}")
    print(f"{'-'*80}")

    username = instance.owner.username
    project_name = instance.name

    # Main CAS directory
    cas_path = get_project_storage_path(username, project_name)

    # Legacy directories
    legacy_paths = [
        os.path.join(settings.MEDIA_ROOT, 'projects_storage', username, project_name),
        os.path.join(settings.MEDIA_ROOT, 'projects', username, project_name),
        os.path.join(settings.MEDIA_ROOT, 'samples', username, project_name),
    ]

    directories = [cas_path] + legacy_paths

    deleted_count = 0
    total_size = 0

    for path in directories:
        if os.path.exists(path):
            try:
                size = get_directory_size(path)
                total_size += size

                shutil.rmtree(path)
                deleted_count += 1

                print(f"[DELETED] {path}")
                print(f"          Size Freed: {size / (1024 * 1024):.2f} MB")
            except Exception as e:
                print(f"[ERROR] Failed deleting {path}: {e}")
        else:
            print(f"[SKIPPED] Not found: {path}")

    cleanup_empty_parent_directories(username)

    print(f"{'-'*80}")
    print(f"[SUMMARY]")
    print(f"Directories deleted: {deleted_count}")
    print(f"Total space freed: {total_size / (1024 * 1024):.2f} MB")
    print(f"[FILESYSTEM CLEANUP] Completed\n")


# ============================================================================
# UTILITIES
# ============================================================================

def get_directory_size(directory):
    """Calculate total directory size in bytes"""
    total_size = 0
    for root, dirs, files in os.walk(directory):
        for f in files:
            try:
                fp = os.path.join(root, f)
                if os.path.exists(fp):
                    total_size += os.path.getsize(fp)
            except Exception:
                continue
    return total_size


def cleanup_empty_parent_directories(username):
    """
    Removes empty user-level directories after project deletion
    """

    print("[CLEANUP] Checking empty parent directories...")

    base_dirs = [
        os.path.join(settings.MEDIA_ROOT, 'projects_storage', username),
        os.path.join(settings.MEDIA_ROOT, 'projects', username),
        os.path.join(settings.MEDIA_ROOT, 'samples', username),
    ]

    for path in base_dirs:
        try:
            if os.path.exists(path) and not os.listdir(path):
                os.rmdir(path)
                print(f"[REMOVED EMPTY DIR] {path}")

                root_path = os.path.dirname(path)
                if os.path.exists(root_path) and not os.listdir(root_path):
                    os.rmdir(root_path)
                    print(f"[REMOVED ROOT DIR] {root_path}")

        except Exception as e:
            print(f"[ERROR] Could not remove empty parent: {e}")
