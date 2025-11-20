"""
versions/download_tasks.py
Celery tasks for creating temporary download ZIPs
Works with file-based manifest storage
"""

import os
import tempfile
import zipfile
from celery import shared_task
from django.conf import settings
from .models import DownloadRequest, Version, get_version_storage_path
from .restore_utils import restore_version_to_directory


def update_download_progress(download: DownloadRequest, progress: int, message: str):
    """
    Update download request progress
    
    Args:
        download: DownloadRequest instance
        progress: Progress percentage (0-100)
        message: Status message
    """
    download.progress = progress
    download.message = message
    download.save(update_fields=['progress', 'message'])


@shared_task(bind=True)
def create_download_zip(self, download_id):
    """
    Create a temporary ZIP file for download
    Works with file-based manifest storage
    
    Args:
        download_id: DownloadRequest ID
    
    Returns:
        Status message string
    """
    try:
        download = DownloadRequest.objects.select_related(
            'version', 
            'version__project', 
            'requested_by'
        ).get(id=download_id)
        
        version = download.version
        
        # Check if version is ready
        if not version.is_ready():
            download.mark_failed(f"Version is not ready (status: {version.status})")
            return f"Version not ready"
        
        download.status = 'processing'
        download.save()
        
        update_download_progress(download, 5, "Initializing download preparation...")
        
        # Create temp directory
        temp_dir = tempfile.mkdtemp(prefix='dawlogs_download_')
        
        try:
            # If it's a snapshot, copy directly
            if version.is_snapshot and version.file:
                update_download_progress(download, 50, "Using existing snapshot...")
                
                snapshot_path = version.file.path
                
                if not os.path.exists(snapshot_path):
                    download.mark_failed(f"Snapshot file not found: {snapshot_path}")
                    return "Snapshot file not found"
                
                file_size = os.path.getsize(snapshot_path)
                
                # Copy to temp location
                import shutil
                temp_zip = os.path.join(temp_dir, 'download.zip')
                shutil.copy2(snapshot_path, temp_zip)
                
                update_download_progress(download, 90, "Finalizing download...")
                
                download.mark_completed(temp_zip, file_size)
                
                # Cleanup
                shutil.rmtree(temp_dir, ignore_errors=True)
                
                return f"Snapshot ZIP ready ({round(file_size / 1024 / 1024, 2)} MB)"
            
            # For CAS versions, restore and create ZIP
            update_download_progress(download, 20, "Restoring version from CAS storage...")
            
            # Check if manifest file exists
            if not version.manifest_file_path:
                download.mark_failed("Version has no manifest file path stored")
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return "No manifest file path"
            
            manifest_file = os.path.join(settings.MEDIA_ROOT, version.manifest_file_path)
            if not os.path.exists(manifest_file):
                download.mark_failed(f"Manifest file not found: {manifest_file}")
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return "Manifest file not found"
            
            # Restore files
            restore_dir = os.path.join(temp_dir, 'restored_files')
            os.makedirs(restore_dir, exist_ok=True)
            
            print(f"Restoring version {version.id} to {restore_dir}")
            
            stats = restore_version_to_directory(version, restore_dir)
            
            if not stats['success']:
                error_msg = '; '.join(stats.get('errors', ['Unknown error']))
                print(f"Restoration failed: {error_msg}")
                download.mark_failed(f"Failed to restore version: {error_msg}")
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return f"Restoration failed"
            
            if stats['files_restored'] == 0:
                download.mark_failed("No files were restored from version")
                import shutil
                shutil.rmtree(temp_dir, ignore_errors=True)
                return "No files restored"
            
            update_download_progress(
                download, 60,
                f"Restored {stats['files_restored']} files, creating ZIP..."
            )
            
            # Create ZIP file
            zip_path = os.path.join(temp_dir, 'download.zip')
            
            files_zipped = 0
            total_files = stats['files_restored']
            
            print(f"Creating ZIP at {zip_path}")
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(restore_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, restore_dir)
                        zipf.write(file_path, arcname)
                        
                        files_zipped += 1
                        if files_zipped % 10 == 0:
                            progress = 60 + int((files_zipped / total_files) * 25)
                            update_download_progress(
                                download, progress,
                                f"Compressing files ({files_zipped}/{total_files})..."
                            )
            
            file_size = os.path.getsize(zip_path)
            
            print(f"ZIP created: {round(file_size / 1024 / 1024, 2)} MB")
            
            update_download_progress(download, 90, "Finalizing download...")
            
            # Mark as completed
            download.mark_completed(zip_path, file_size)
            
            # Cleanup temp directory
            import shutil
            shutil.rmtree(temp_dir, ignore_errors=True)
            
            file_size_mb = round(file_size / (1024 * 1024), 2)
            return f"ZIP created successfully ({file_size_mb} MB)"
        
        except Exception as e:
            # Cleanup on error
            import shutil
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
    
    except DownloadRequest.DoesNotExist:
        return "Download request not found"
    
    except Exception as e:
        try:
            download = DownloadRequest.objects.get(id=download_id)
            download.mark_failed(str(e))
        except Exception:
            pass
        
        print(f"Error in create_download_zip: {str(e)}")
        import traceback
        traceback.print_exc()
        return str(e)


@shared_task
def cleanup_expired_downloads():
    """
    Periodic task to cleanup expired download requests
    Run daily via Celery Beat
    
    Returns:
        Status message string
    """
    from django.utils import timezone
    
    expired_downloads = DownloadRequest.objects.filter(
        status='completed',
        expires_at__lt=timezone.now()
    )
    
    count = 0
    for download in expired_downloads:
        try:
            download.status = 'expired'
            download.save()
            download.delete()  # Triggers file deletion
            count += 1
        except Exception as e:
            print(f"Error cleaning up download {download.id}: {e}")
    
    return f"Cleaned up {count} expired downloads"