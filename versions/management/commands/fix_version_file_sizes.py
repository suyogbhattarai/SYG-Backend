"""
Management command to fix file sizes for existing versions
Run this: python manage.py fix_version_file_sizes
"""

import os
import json
from django.core.management.base import BaseCommand
from django.conf import settings
from versions.models import Version


class Command(BaseCommand):
    help = 'Fix file sizes for existing versions'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Find versions without file size
        versions_without_size = Version.objects.filter(file_size__isnull=True, status='completed')
        
        self.stdout.write(f'Found {versions_without_size.count()} versions without file size')
        
        fixed_count = 0
        error_count = 0
        
        for version in versions_without_size:
            try:
                total_size = 0
                
                if version.is_snapshot:
                    # Get size from snapshot file
                    if version.file and os.path.exists(version.file.path):
                        total_size = os.path.getsize(version.file.path)
                    else:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Version {version.id} (v{version.get_version_number()}): '
                                f'Snapshot file not found'
                            )
                        )
                        error_count += 1
                        continue
                else:
                    # Calculate from manifest
                    if not version.manifest_file_path:
                        self.stdout.write(
                            self.style.ERROR(
                                f'Version {version.id} (v{version.get_version_number()}): '
                                f'No manifest file path'
                            )
                        )
                        error_count += 1
                        continue
                    
                    manifest_file = os.path.join(settings.MEDIA_ROOT, version.manifest_file_path)
                    
                    if not os.path.exists(manifest_file):
                        self.stdout.write(
                            self.style.ERROR(
                                f'Version {version.id} (v{version.get_version_number()}): '
                                f'Manifest file not found'
                            )
                        )
                        error_count += 1
                        continue
                    
                    # Load manifest and sum file sizes
                    with open(manifest_file, 'r', encoding='utf-8') as f:
                        manifest = json.load(f)
                    
                    for file_entry in manifest.get('files', []):
                        total_size += file_entry.get('size', 0)
                
                if not dry_run:
                    version.file_size = total_size
                    version.save(update_fields=['file_size'])
                
                size_mb = round(total_size / (1024 * 1024), 2)
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Version {version.id} (v{version.get_version_number()}): '
                        f'{"Would set" if dry_run else "Set"} file_size to {size_mb} MB'
                    )
                )
                
                fixed_count += 1
                
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(
                        f'Version {version.id}: Error - {str(e)}'
                    )
                )
                error_count += 1
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(f'Summary:'))
        self.stdout.write(f'  Fixed: {fixed_count}')
        self.stdout.write(f'  Errors: {error_count}')
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN - No changes were made'))
            self.stdout.write('Run without --dry-run to apply changes')