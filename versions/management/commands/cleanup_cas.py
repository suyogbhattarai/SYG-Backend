"""
Management command to clean up unreferenced CAS blobs
FIXED: Proper file and directory cleanup
"""

import os
from django.core.management.base import BaseCommand
from django.conf import settings
from versions.models import FileBlob


class Command(BaseCommand):
    help = 'Clean up CAS blobs with zero references'

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
        self.stdout.write("CAS Blob Cleanup Utility")
        self.stdout.write("=" * 60)
        self.stdout.write("")
        
        # Find unreferenced blobs
        unreferenced_blobs = FileBlob.objects.filter(ref_count__lte=0)
        
        if not unreferenced_blobs.exists():
            self.stdout.write(self.style.SUCCESS("✓ No unreferenced blobs found"))
            return
        
        # Calculate stats
        total_blobs = unreferenced_blobs.count()
        total_size = sum(blob.size for blob in unreferenced_blobs)
        total_size_mb = round(total_size / (1024 * 1024), 2)
        
        self.stdout.write(f"Found {total_blobs} unreferenced blobs")
        self.stdout.write(f"Total size: {total_size_mb} MB")
        self.stdout.write("")
        
        # Show sample
        self.stdout.write("Sample blobs to be deleted:")
        for blob in unreferenced_blobs[:5]:
            self.stdout.write(f"  - {blob.hash[:16]}... ({blob.get_size_mb()} MB, ref_count: {blob.ref_count})")
        
        if total_blobs > 5:
            self.stdout.write(f"  ... and {total_blobs - 5} more")
        
        self.stdout.write("")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN - No files will be deleted"))
            return
        
        # Confirm deletion
        if not force:
            confirm = input(f"Delete {total_blobs} blobs ({total_size_mb} MB)? [y/N]: ")
            if confirm.lower() != 'y':
                self.stdout.write(self.style.WARNING("Cancelled"))
                return
        
        # Delete blobs
        deleted_count = 0
        deleted_size = 0
        errors = []
        
        for blob in unreferenced_blobs:
            try:
                deleted_size += blob.size
                blob.delete()  # Signals handle file deletion
                deleted_count += 1
                
            except Exception as e:
                errors.append(f"Error deleting {blob.hash[:16]}: {str(e)}")
        
        # Report results
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"✓ Deleted {deleted_count} blobs"))
        self.stdout.write(f"  Freed: {round(deleted_size / (1024 * 1024), 2)} MB")
        
        if errors:
            self.stdout.write("")
            self.stdout.write(self.style.ERROR(f"Errors ({len(errors)}):"))
            for error in errors[:10]:
                self.stdout.write(f"  - {error}")
            if len(errors) > 10:
                self.stdout.write(f"  ... and {len(errors) - 10} more errors")
        
        # Cleanup empty blob directories
        self.stdout.write("")
        self.stdout.write("Cleaning up empty blob directories...")
        
        cas_blobs_dir = os.path.join(settings.MEDIA_ROOT, 'cas_blobs')
        if os.path.exists(cas_blobs_dir):
            removed_dirs = 0
            for hash_prefix in os.listdir(cas_blobs_dir):
                prefix_dir = os.path.join(cas_blobs_dir, hash_prefix)
                if os.path.isdir(prefix_dir) and not os.listdir(prefix_dir):
                    try:
                        os.rmdir(prefix_dir)
                        removed_dirs += 1
                    except Exception as e:
                        self.stdout.write(f"  Error removing {prefix_dir}: {e}")
            
            if removed_dirs > 0:
                self.stdout.write(f"  Removed {removed_dirs} empty directories")