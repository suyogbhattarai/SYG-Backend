"""
Management command to perform comprehensive cleanup
Runs all cleanup operations in one command
"""

from django.core.management.base import BaseCommand
from django.core.management import call_command


class Command(BaseCommand):
    help = 'Perform comprehensive cleanup of CAS blobs, orphaned files, and expired downloads'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Skip confirmation prompts',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        self.stdout.write("=" * 60)
        self.stdout.write("COMPREHENSIVE CLEANUP")
        self.stdout.write("=" * 60)
        self.stdout.write("")
        
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY RUN MODE - No files will be deleted"))
            self.stdout.write("")
        
        # 1. Cleanup expired downloads
        self.stdout.write(self.style.HTTP_INFO("Step 1: Cleaning up expired downloads..."))
        self.stdout.write("")
        
        from django.utils import timezone
        from versions.models import DownloadRequest
        
        expired = DownloadRequest.objects.filter(
            status='completed',
            expires_at__lt=timezone.now()
        )
        
        if expired.exists():
            count = expired.count()
            self.stdout.write(f"Found {count} expired downloads")
            
            if not dry_run:
                if not force:
                    confirm = input(f"Delete {count} expired downloads? [y/N]: ")
                    if confirm.lower() != 'y':
                        self.stdout.write(self.style.WARNING("Skipped"))
                    else:
                        for download in expired:
                            try:
                                download.delete()
                            except Exception as e:
                                self.stdout.write(f"Error: {e}")
                        self.stdout.write(self.style.SUCCESS(f"✓ Deleted {count} expired downloads"))
                else:
                    for download in expired:
                        try:
                            download.delete()
                        except Exception as e:
                            self.stdout.write(f"Error: {e}")
                    self.stdout.write(self.style.SUCCESS(f"✓ Deleted {count} expired downloads"))
        else:
            self.stdout.write(self.style.SUCCESS("✓ No expired downloads found"))
        
        self.stdout.write("")
        
        # 2. Cleanup unreferenced CAS blobs
        self.stdout.write(self.style.HTTP_INFO("Step 2: Cleaning up unreferenced CAS blobs..."))
        self.stdout.write("")
        
        try:
            call_command(
                'cleanup_cas',
                dry_run=dry_run,
                force=force,
                stdout=self.stdout,
                stderr=self.stderr
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error running cleanup_cas: {e}"))
        
        self.stdout.write("")
        
        # 3. Cleanup orphaned directories
        self.stdout.write(self.style.HTTP_INFO("Step 3: Cleaning up orphaned directories..."))
        self.stdout.write("")
        
        try:
            call_command(
                'cleanup_orphaned',
                dry_run=dry_run,
                force=force,
                stdout=self.stdout,
                stderr=self.stderr
            )
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"Error running cleanup_orphaned: {e}"))
        
        self.stdout.write("")
        self.stdout.write("=" * 60)
        self.stdout.write(self.style.SUCCESS("✓ CLEANUP COMPLETE"))
        self.stdout.write("=" * 60)