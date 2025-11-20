"""
Management command to clean up orphaned directories and files
Removes project directories that no longer have database records
"""

import os
import shutil
from django.core.management.base import BaseCommand
from django.conf import settings
from projects.models import Project
from versions.models import Version


class Command(BaseCommand):
    help = 'Clean up orphaned project directories and files'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompt',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write("=" * 60)
        self.stdout.write("Orphaned Files Cleanup Utility")
        self.stdout.write("=" * 60)
        self.stdout.write("")
        
        orphaned_items = []
        total_size = 0
        
        # Check users directory
        users_dir = os.path.join(settings.MEDIA_ROOT, 'users')
        if os.path.exists(users_dir):
            self.stdout.write("Scanning users directory...")
            
            for username in os.listdir(users_dir):
                user_dir = os.path.join(users_dir, username)
                if not os.path.isdir(user_dir):
                    continue
                
                projects_dir = os.path.join(user_dir, 'projects')
                if not os.path.exists(projects_dir):
                    continue
                
                for project_name in os.listdir(projects_dir):
                    project_dir = os.path.join(projects_dir, project_name)
                    if not os.path.isdir(project_dir):
                        continue
                    
                    # Check if project exists in database
                    project_exists = Project.objects.filter(
                        owner__username=username,
                        name=project_name
                    ).exists()
                    
                    if not project_exists:
                        dir_size = self._get_directory_size(project_dir)
                        orphaned_items.append({
                            'path': project_dir,
                            'type': 'project',
                            'size': dir_size
                        })
                        total_size += dir_size
        
        # Check old projects_storage directory
        old_storage_dir = os.path.join(settings.MEDIA_ROOT, 'projects_storage')
        if os.path.exists(old_storage_dir):
            self.stdout.write("Scanning old projects_storage directory...")
            
            for username in os.listdir(old_storage_dir):
                user_dir = os.path.join(old_storage_dir, username)
                if not os.path.isdir(user_dir):
                    continue
                
                for project_name in os.listdir(user_dir):
                    project_dir = os.path.join(user_dir, project_name)
                    if not os.path.isdir(project_dir):
                        continue
                    
                    # Check if project exists
                    project_exists = Project.objects.filter(
                        owner__username=username,
                        name=project_name
                    ).exists()
                    
                    if not project_exists:
                        dir_size = self._get_directory_size(project_dir)
                        orphaned_items.append({
                            'path': project_dir,
                            'type': 'old_project',
                            'size': dir_size
                        })
                        total_size += dir_size
        
        # Report findings
        if not orphaned_items:
            self.stdout.write(self.style.SUCCESS("✓ No orphaned directories found"))
            return
        
        total_size_mb = round(total_size / (1024 * 1024), 2)
        
        self.stdout.write(f"Found {len(orphaned_items)} orphaned directories")
        self.stdout.write(f"Total size: {total_size_mb} MB")
        self.stdout.write("")
        
        # Show sample
        self.stdout.write("Sample orphaned directories:")
        for item in orphaned_items[:10]:
            item_size_mb = round(item['size'] / (1024 * 1024), 2)
            self.stdout.write(f"  - {item['path']} ({item_size_mb} MB)")
        
        if len(orphaned_items) > 10:
            self.stdout.write(f"  ... and {len(orphaned_items) - 10} more")
        
        self.stdout.write("")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No directories will be deleted"))
            return
        
        # Confirm deletion
        if not force:
            confirm = input(f"Delete {len(orphaned_items)} orphaned directories ({total_size_mb} MB)? [y/N]: ")
            if confirm.lower() != 'y':
                self.stdout.write(self.style.WARNING("Cancelled"))
                return
        
        # Delete orphaned directories
        deleted_count = 0
        deleted_size = 0
        errors = []
        
        for item in orphaned_items:
            try:
                shutil.rmtree(item['path'], ignore_errors=False)
                deleted_count += 1
                deleted_size += item['size']
                self.stdout.write(f"  Deleted: {item['path']}")
            except Exception as e:
                errors.append(f"Error deleting {item['path']}: {str(e)}")
        
        # Report results
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"✓ Deleted {deleted_count} directories"))
        self.stdout.write(f"  Freed: {round(deleted_size / (1024 * 1024), 2)} MB")
        
        if errors:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"Errors ({len(errors)}):"))
            for error in errors[:10]:
                self.stdout.write(f"  - {error}")
            if len(errors) > 10:
                self.stdout.write(f"  ... and {len(errors) - 10} more errors")
        
        # Cleanup empty parent directories
        self.stdout.write("")
        self.stdout.write("Cleaning up empty parent directories...")
        self._cleanup_empty_parents()
    
    def _get_directory_size(self, path):
        """Calculate total size of directory"""
        total = 0
        try:
            for dirpath, dirnames, filenames in os.walk(path):
                for filename in filenames:
                    filepath = os.path.join(dirpath, filename)
                    if os.path.exists(filepath):
                        total += os.path.getsize(filepath)
        except Exception:
            pass
        return total
    
    def _cleanup_empty_parents(self):
        """Remove empty parent directories"""
        removed = 0
        
        # Clean users directory
        users_dir = os.path.join(settings.MEDIA_ROOT, 'users')
        if os.path.exists(users_dir):
            for username in os.listdir(users_dir):
                user_dir = os.path.join(users_dir, username)
                if not os.path.isdir(user_dir):
                    continue
                
                projects_dir = os.path.join(user_dir, 'projects')
                if os.path.exists(projects_dir) and not os.listdir(projects_dir):
                    try:
                        os.rmdir(projects_dir)
                        removed += 1
                    except:
                        pass
                
                if os.path.exists(user_dir) and not os.listdir(user_dir):
                    try:
                        os.rmdir(user_dir)
                        removed += 1
                    except:
                        pass
        
        # Clean old projects_storage directory
        old_storage_dir = os.path.join(settings.MEDIA_ROOT, 'projects_storage')
        if os.path.exists(old_storage_dir):
            for username in os.listdir(old_storage_dir):
                user_dir = os.path.join(old_storage_dir, username)
                if os.path.isdir(user_dir) and not os.listdir(user_dir):
                    try:
                        os.rmdir(user_dir)
                        removed += 1
                    except:
                        pass
            
            if not os.listdir(old_storage_dir):
                try:
                    os.rmdir(old_storage_dir)
                    removed += 1
                except:
                    pass
        
        if removed > 0:
            self.stdout.write(f"  Removed {removed} empty directories")