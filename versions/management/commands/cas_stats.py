# versions/management/commands/cas_stats.py
"""
Management command to show CAS storage statistics
"""

from django.core.management.base import BaseCommand
from django.db.models import Sum, Count
from versions.models import FileBlob, Version


class Command(BaseCommand):
    help = 'Show CAS storage statistics'

    def handle(self, *args, **options):
        self.stdout.write("=" * 60)
        self.stdout.write("CAS Storage Statistics")
        self.stdout.write("=" * 60)
        self.stdout.write("")
        
        # Blob statistics
        total_blobs = FileBlob.objects.count()
        total_blob_size = FileBlob.objects.aggregate(Sum('size'))['size__sum'] or 0
        referenced_blobs = FileBlob.objects.filter(ref_count__gt=0).count()
        unreferenced_blobs = FileBlob.objects.filter(ref_count=0).count()
        
        self.stdout.write("📦 BLOB STORAGE:")
        self.stdout.write(f"  Total blobs: {total_blobs}")
        self.stdout.write(f"  Referenced: {referenced_blobs}")
        self.stdout.write(f"  Unreferenced: {unreferenced_blobs}")
        self.stdout.write(f"  Total size: {round(total_blob_size / (1024 ** 3), 2)} GB")
        self.stdout.write("")
        
        # Version statistics
        total_versions = Version.objects.count()
        snapshot_versions = Version.objects.filter(is_snapshot=True).count()
        cas_versions = Version.objects.filter(is_snapshot=False).count()
        
        snapshot_size = Version.objects.filter(is_snapshot=True).aggregate(Sum('file_size'))['file_size__sum'] or 0
        cas_size = Version.objects.filter(is_snapshot=False).aggregate(Sum('file_size'))['file_size__sum'] or 0
        
        self.stdout.write("📝 VERSIONS:")
        self.stdout.write(f"  Total versions: {total_versions}")
        self.stdout.write(f"  Snapshot versions: {snapshot_versions}")
        self.stdout.write(f"  CAS versions: {cas_versions}")
        self.stdout.write("")
        
        self.stdout.write("💾 STORAGE BREAKDOWN:")
        self.stdout.write(f"  Snapshots: {round(snapshot_size / (1024 ** 3), 2)} GB ({snapshot_versions} versions)")
        self.stdout.write(f"  CAS (logical): {round(cas_size / (1024 ** 3), 2)} GB ({cas_versions} versions)")
        self.stdout.write(f"  CAS (physical): {round(total_blob_size / (1024 ** 3), 2)} GB (deduplicated)")
        self.stdout.write("")
        
        # Calculate savings
        if cas_size > 0:
            savings = cas_size - total_blob_size
            savings_pct = (savings / cas_size) * 100
            self.stdout.write("💰 SAVINGS FROM DEDUPLICATION:")
            self.stdout.write(f"  Saved: {round(savings / (1024 ** 3), 2)} GB ({round(savings_pct, 1)}%)")
            self.stdout.write("")
        
        # Reference count distribution
        self.stdout.write("📊 REFERENCE COUNT DISTRIBUTION:")
        ref_counts = FileBlob.objects.values('ref_count').annotate(count=Count('id')).order_by('-ref_count')
        
        for item in ref_counts[:10]:
            ref = item['ref_count']
            count = item['count']
            self.stdout.write(f"  {ref} refs: {count} blobs")
        
        if len(ref_counts) > 10:
            self.stdout.write(f"  ... and {len(ref_counts) - 10} more reference counts")
        
        self.stdout.write("")
        
        # Top 10 largest blobs
        self.stdout.write("🔝 TOP 10 LARGEST BLOBS:")
        large_blobs = FileBlob.objects.order_by('-size')[:10]
        
        for blob in large_blobs:
            self.stdout.write(f"  {blob.hash[:16]}... - {blob.get_size_mb()} MB (refs: {blob.ref_count})")
        
        self.stdout.write("")
        self.stdout.write("=" * 60)