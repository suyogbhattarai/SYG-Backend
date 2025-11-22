
from django.core.management.base import BaseCommand
from versions.models import FileBlob

class Command(BaseCommand):
    help = 'Cleanup unused CAS blobs (ref_count = 0)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be deleted without actually deleting',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        unused_blobs = FileBlob.objects.filter(ref_count__lte=0)
        count = unused_blobs.count()
        total_size = sum(blob.size for blob in unused_blobs)
        
        self.stdout.write(f"\nFound {count} unused blobs")
        self.stdout.write(f"Total size: {round(total_size / (1024 * 1024), 2)} MB")
        
        if dry_run:
            self.stdout.write(self.style.WARNING('\nDRY RUN - Nothing deleted'))
            for blob in unused_blobs[:10]:
                self.stdout.write(f"  Would delete: {blob.hash[:16]}... ({blob.get_size_mb()} MB)")
            if count > 10:
                self.stdout.write(f"  ... and {count - 10} more")
        else:
            confirm = input(f"\nDelete {count} blobs? (yes/no): ")
            if confirm.lower() == 'yes':
                for blob in unused_blobs:
                    self.stdout.write(f"Deleting: {blob.hash[:16]}...")
                    blob.delete()
                self.stdout.write(self.style.SUCCESS(f'\n✓ Deleted {count} blobs'))
            else:
                self.stdout.write(self.style.WARNING('Cancelled'))
