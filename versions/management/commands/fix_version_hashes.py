"""
Management command to fix existing versions with null hashes
Run this: python manage.py fix_version_hashes
"""

import os
import json
import hashlib
from django.core.management.base import BaseCommand
from django.conf import settings
from versions.models import Version


class Command(BaseCommand):
    help = 'Fix existing versions with null hashes by recalculating from manifests'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='Recalculate hash even if it already exists',
        )

    def compute_manifest_hash(self, manifest):
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

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        force = options['force']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Find versions to fix
        if force:
            versions_to_fix = Version.objects.filter(status='completed')
            self.stdout.write(f'Force mode: Processing all {versions_to_fix.count()} completed versions')
        else:
            versions_to_fix = Version.objects.filter(hash__isnull=True, status='completed')
            self.stdout.write(f'Found {versions_to_fix.count()} versions with null hash')
        
        if versions_to_fix.count() == 0:
            self.stdout.write(self.style.SUCCESS('No versions need fixing!'))
            return
        
        fixed_count = 0
        skipped_count = 0
        error_count = 0
        
        for version in versions_to_fix:
            try:
                version_num = version.get_version_number()
                
                # Skip snapshots - they can't have hashes recalculated from manifests
                if version.is_snapshot:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Version {version.id} (v{version_num}): '
                            f'Snapshot version - skipping (snapshots use file-based hashing)'
                        )
                    )
                    skipped_count += 1
                    continue
                
                # Load manifest
                if not version.manifest_file_path:
                    self.stdout.write(
                        self.style.ERROR(
                            f'Version {version.id} (v{version_num}): '
                            f'No manifest file path'
                        )
                    )
                    error_count += 1
                    continue
                
                manifest_file = os.path.join(settings.MEDIA_ROOT, version.manifest_file_path)
                
                if not os.path.exists(manifest_file):
                    self.stdout.write(
                        self.style.ERROR(
                            f'Version {version.id} (v{version_num}): '
                            f'Manifest file not found: {manifest_file}'
                        )
                    )
                    error_count += 1
                    continue
                
                # Load and compute hash
                with open(manifest_file, 'r', encoding='utf-8') as f:
                    manifest = json.load(f)
                
                manifest_hash = self.compute_manifest_hash(manifest)
                
                if not dry_run:
                    version.hash = manifest_hash
                    version.save(update_fields=['hash'])
                
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Version {version.id} (v{version_num}): '
                        f'{"Would set" if dry_run else "Set"} hash to {manifest_hash[:16]}...'
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
                import traceback
                traceback.print_exc()
        
        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS('='*50))
        self.stdout.write(self.style.SUCCESS('Summary:'))
        self.stdout.write(f'  Fixed: {fixed_count}')
        self.stdout.write(f'  Skipped: {skipped_count}')
        self.stdout.write(f'  Errors: {error_count}')
        self.stdout.write(self.style.SUCCESS('='*50))
        
        if dry_run:
            self.stdout.write('')
            self.stdout.write(self.style.WARNING('DRY RUN - No changes were made'))
            self.stdout.write(self.style.WARNING('Run without --dry-run to apply changes'))
        else:
            self.stdout.write('')
            self.stdout.write(self.style.SUCCESS('✓ Hash fixing complete!'))