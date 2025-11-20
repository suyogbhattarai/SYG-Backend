# versions/management/commands/cleanup_downloads.py
"""
Management command to cleanup expired downloads
Run this daily: python manage.py cleanup_downloads
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
from versions.models import DownloadRequest


class Command(BaseCommand):
    help = 'Cleanup expired download requests'
    
    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )
    
    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        # Find expired downloads
        expired_downloads = DownloadRequest.objects.filter(
            status='completed',
            expires_at__lt=timezone.now()
        )
        
        count = expired_downloads.count()
        
        if count == 0:
            self.stdout.write(self.style.SUCCESS('No expired downloads found'))
            return
        
        if dry_run:
            self.stdout.write(self.style.WARNING(f'Would delete {count} expired downloads:'))
            for download in expired_downloads:
                self.stdout.write(f'  - Download {download.id} for version {download.version.id} (expired: {download.expires_at})')
            return
        
        # Delete expired downloads
        deleted = 0
        for download in expired_downloads:
            try:
                version_id = download.version.id
                download.status = 'expired'
                download.save()
                download.delete()
                deleted += 1
                self.stdout.write(f'Deleted download {download.id} for version {version_id}')
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'Error deleting download {download.id}: {e}'))
        
        self.stdout.write(self.style.SUCCESS(f'Successfully deleted {deleted} expired downloads'))