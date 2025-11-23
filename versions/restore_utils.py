"""
versions/restore_utils.py
Utilities for restoring versions from CAS or snapshots
Works with file-based manifest storage and project ID paths
"""

import os
import base64
import zipfile
import tempfile
from django.conf import settings
from .models import Version, FileBlob


def restore_version_to_directory(version: Version, target_dir: str) -> dict:
    """
    Restore a version to a target directory
    Handles both snapshot and CAS manifest versions
    
    Args:
        version: Version instance
        target_dir: Directory to restore files to
    
    Returns:
        dict with keys:
            - success: bool
            - files_restored: int
            - total_size: int
            - storage_type: str ('snapshot' or 'cas')
            - errors: list
    """
    os.makedirs(target_dir, exist_ok=True)
    
    stats = {
        'success': False,
        'files_restored': 0,
        'total_size': 0,
        'storage_type': 'snapshot' if version.is_snapshot else 'cas',
        'errors': []
    }
    
    try:
        if version.is_snapshot:
            stats.update(_restore_from_snapshot(version, target_dir))
        else:
            stats.update(_restore_from_manifest(version, target_dir))
        
        stats['success'] = len(stats['errors']) == 0
        
    except Exception as e:
        stats['errors'].append(f"Fatal error: {str(e)}")
        stats['success'] = False
        import traceback
        traceback.print_exc()
    
    return stats


def _restore_from_snapshot(version: Version, target_dir: str) -> dict:
    """Restore files from ZIP snapshot"""
    stats = {'files_restored': 0, 'total_size': 0, 'errors': []}
    
    if not version.file:
        raise ValueError("Snapshot version has no file attached")
    
    zip_path = version.file.path
    
    if not os.path.exists(zip_path):
        raise FileNotFoundError(f"Snapshot file not found: {zip_path}")
    
    print(f"Extracting snapshot from: {zip_path}")
    
    try:
        with zipfile.ZipFile(zip_path, 'r') as zipf:
            zipf.extractall(target_dir)
            
            for info in zipf.filelist:
                if not info.is_dir():
                    stats['files_restored'] += 1
                    stats['total_size'] += info.file_size
    
    except Exception as e:
        stats['errors'].append(f"Error extracting snapshot: {str(e)}")
    
    return stats


def _restore_from_manifest(version: Version, target_dir: str) -> dict:
    """
    Restore files from CAS manifest stored in file
    
    Args:
        version: Version instance
        target_dir: Directory to restore files to
    
    Returns:
        dict with restoration stats
    """
    stats = {'files_restored': 0, 'total_size': 0, 'errors': []}
    
    # Load manifest from file
    manifest = version.load_manifest_from_file()
    
    if not manifest:
        raise ValueError("CAS version has no manifest file or manifest file not found")
    
    files = manifest.get('files', [])
    
    print(f"Restoring {len(files)} files from CAS manifest")
    
    for file_entry in files:
        try:
            rel_path = file_entry.get('path')
            storage_type = file_entry.get('storage')
            
            if not rel_path:
                stats['errors'].append("File entry missing path")
                continue
            
            dest_path = os.path.join(target_dir, rel_path)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            
            if storage_type == 'cas':
                # Restore from CAS blob
                blob_id = file_entry.get('blob_id')
                
                if not blob_id:
                    stats['errors'].append(f"No blob_id for {rel_path}")
                    continue
                
                try:
                    blob = FileBlob.objects.get(id=blob_id)
                    blob_path = blob.file.path
                    
                    if not os.path.exists(blob_path):
                        stats['errors'].append(f"Blob file not found: {blob_path} for {rel_path}")
                        continue
                    
                    print(f"Restoring CAS file: {rel_path} from blob {blob_id}")
                    
                    # Copy blob file to destination
                    import shutil
                    shutil.copy2(blob_path, dest_path)
                    
                    stats['files_restored'] += 1
                    stats['total_size'] += blob.size
                    
                except FileBlob.DoesNotExist:
                    stats['errors'].append(f"Blob {blob_id} not found for {rel_path}")
                    continue
                except Exception as e:
                    stats['errors'].append(f"Error restoring CAS file {rel_path}: {str(e)}")
                    continue
                
            elif storage_type == 'inline':
                # Restore from inline base64 content
                content_b64 = file_entry.get('content')
                
                if not content_b64:
                    stats['errors'].append(f"No content for inline file {rel_path}")
                    continue
                
                try:
                    content = base64.b64decode(content_b64)
                    
                    with open(dest_path, 'wb') as f:
                        f.write(content)
                    
                    print(f"Restoring inline file: {rel_path}")
                    
                    stats['files_restored'] += 1
                    stats['total_size'] += len(content)
                    
                except Exception as e:
                    stats['errors'].append(f"Error restoring inline file {rel_path}: {str(e)}")
                    continue
            else:
                stats['errors'].append(f"Unknown storage type '{storage_type}' for {rel_path}")
        
        except Exception as e:
            stats['errors'].append(f"Error processing {rel_path}: {str(e)}")
    
    print(f"Restoration complete: {stats['files_restored']} files restored, {len(stats['errors'])} errors")
    
    return stats


def create_version_zip_on_demand(version: Version) -> str:
    """
    Create a ZIP file from a version on-demand
    
    Args:
        version: Version instance
    
    Returns:
        Path to created ZIP file
    
    Raises:
        Exception if restoration fails
    """
    if version.is_snapshot and version.file:
        # Already a ZIP, return path
        return version.file.path
    
    # Create temporary directory for restoration
    with tempfile.TemporaryDirectory() as temp_dir:
        # Restore files
        stats = restore_version_to_directory(version, temp_dir)
        
        if not stats['success'] or stats['files_restored'] == 0:
            error_msg = '; '.join(stats['errors']) if stats['errors'] else 'Unknown error'
            raise Exception(f"Failed to restore version: {error_msg}")
        
        # Create ZIP
        zip_name = f"{version.project.name}_v{version.version_number}.zip"
        zip_path = os.path.join(tempfile.gettempdir(), zip_name)
        
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(temp_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, temp_dir)
                    zipf.write(file_path, arcname)
        
        return zip_path


def get_version_file_list(version: Version) -> list:
    """
    Get list of files in a version
    
    Args:
        version: Version instance
    
    Returns:
        list of dicts with file information
    """
    if version.is_snapshot:
        if not version.file:
            return []
        
        zip_path = version.file.path
        
        if not os.path.exists(zip_path):
            return []
        
        files = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zipf:
                for info in zipf.filelist:
                    if not info.is_dir():
                        files.append({
                            'path': info.filename,
                            'size': info.file_size,
                            'compressed_size': info.compress_size
                        })
        except Exception as e:
            print(f"Error reading snapshot: {e}")
        
        return files
    
    else:
        # Load manifest from file
        manifest = version.load_manifest_from_file()
        
        if not manifest:
            return []
        
        files = []
        for file_entry in manifest.get('files', []):
            files.append({
                'path': file_entry.get('path'),
                'size': file_entry.get('size'),
                'storage': file_entry.get('storage'),
                'hash': file_entry.get('hash')
            })
        
        return files