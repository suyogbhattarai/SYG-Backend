"""
versions/models.py
FIXED: Version folder naming, UUIDs, detailed change tracking, and blob cleanup
"""

import os
import shutil
import json
import uuid
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import pre_delete, post_delete
from django.dispatch import receiver
from django.conf import settings
from projects.models import Project


def sanitize_text(text):
    """Remove null characters and other problematic characters from text"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


def get_user_storage_path(username):
    """Get base storage path for a user"""
    return os.path.join(settings.MEDIA_ROOT, 'users', username)


def get_project_storage_path(username, project_name):
    """Get storage path for a project"""
    return os.path.join(get_user_storage_path(username), 'projects', project_name)


def get_project_master_path(username, project_name):
    """Get master directory path for project files"""
    return os.path.join(get_project_storage_path(username, project_name), 'master')


def get_version_storage_path(username, project_name, version_number):
    """Get storage path for a specific version using version_number"""
    return os.path.join(
        get_project_storage_path(username, project_name), 
        'versions', 
        f'v{version_number}'
    )


def get_manifest_path(username, project_name, version_number):
    """Get storage path for version manifest JSON file"""
    version_dir = get_version_storage_path(username, project_name, version_number)
    return os.path.join(version_dir, 'manifest.json')


def blob_upload_path(instance, filename):
    """Generate upload path for CAS blobs - organized by hash prefix"""
    hash_prefix = instance.hash[:2]
    return os.path.join('cas_blobs', hash_prefix, instance.hash)


def version_snapshot_path(instance, filename):
    """Generate upload path for version snapshots using version_number"""
    version_number = instance.version_number or 'temp'
    return os.path.join(
        'users',
        instance.project.owner.username,
        'projects',
        instance.project.name,
        'versions',
        f'v{version_number}',
        'snapshot.zip'
    )


def download_zip_path(instance, filename):
    """Generate upload path for download ZIPs"""
    version_number = instance.version.version_number or 'unknown'
    return os.path.join(
        'users',
        instance.version.project.owner.username,
        'projects',
        instance.version.project.name,
        'downloads',
        f'v{version_number}_download_{instance.uid}.zip'
    )


class FileBlob(models.Model):
    """
    Content-addressable storage for file contents
    Files >1MB are stored here to enable deduplication
    Automatically cleaned up when ref_count reaches 0
    """
    hash = models.CharField(max_length=64, unique=True, db_index=True)
    file = models.FileField(upload_to=blob_upload_path)
    size = models.BigIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    ref_count = models.IntegerField(default=0)
    
    class Meta:
        verbose_name = 'File Blob (CAS)'
        verbose_name_plural = 'File Blobs (CAS)'
        db_table = 'versions_fileblob'
        indexes = [
            models.Index(fields=['hash']),
            models.Index(fields=['ref_count']),
            models.Index(fields=['created_at']),
        ]
    
    def __str__(self):
        return f"Blob {self.hash[:8]}... ({self.get_size_mb()}MB, refs: {self.ref_count})"
    
    def get_size_mb(self):
        """Get size in megabytes"""
        return round(self.size / (1024 * 1024), 2)
    
    def increment_ref(self):
        """Increment reference count"""
        self.ref_count = models.F('ref_count') + 1
        self.save(update_fields=['ref_count'])
        self.refresh_from_db()
    
    def decrement_ref(self):
        """Decrement reference count and cleanup if no references"""
        self.ref_count = models.F('ref_count') - 1
        self.save(update_fields=['ref_count'])
        self.refresh_from_db()
        
        if self.ref_count <= 0:
            print(f"[BLOB CLEANUP] Deleting unused blob {self.hash[:16]}...")
            self.delete()


@receiver(pre_delete, sender=FileBlob)
def fileblob_pre_delete(sender, instance, **kwargs):
    """Delete blob file from storage before model deletion"""
    if instance.file:
        try:
            file_path = instance.file.path
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"[BLOB] Deleted blob file: {file_path}")
                
                parent_dir = os.path.dirname(file_path)
                if os.path.exists(parent_dir) and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    print(f"[BLOB] Removed empty blob directory: {parent_dir}")
        except Exception as e:
            print(f"[BLOB ERROR] Error deleting blob file: {e}")


class Version(models.Model):
    """
    Version with UUID, proper folder naming, and detailed change tracking
    """
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    uid = models.CharField(max_length=16, unique=True, db_index=True, editable=False)
    
    project = models.ForeignKey(
        Project,
        related_name='versions_new',
        on_delete=models.CASCADE
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='versions_created_new'
    )
    commit_message = models.TextField(null=True, blank=True)
    
    # Version numbering
    version_number = models.IntegerField(null=True, blank=True)
    
    # Version status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    
    # Storage strategy
    is_snapshot = models.BooleanField(default=False)
    file = models.FileField(upload_to=version_snapshot_path, null=True, blank=True)
    
    # Manifest file path (relative to MEDIA_ROOT)
    manifest_file_path = models.CharField(max_length=500, null=True, blank=True)
    
    hash = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_count = models.IntegerField(default=0)
    
    # File change tracking
    files_added = models.IntegerField(default=0)
    files_modified = models.IntegerField(default=0)
    files_deleted = models.IntegerField(default=0)
    size_change = models.BigIntegerField(default=0)
    
    # Detailed change tracking (JSON)
    change_details = models.JSONField(default=dict, blank=True)
    
    previous_version = models.ForeignKey(
        'self',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='next_versions'
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Version (New)'
        verbose_name_plural = 'Versions (New)'
        db_table = 'versions_version'
        indexes = [
            models.Index(fields=['uid']),
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['project', 'hash']),
            models.Index(fields=['project', 'is_snapshot']),
            models.Index(fields=['project', 'status']),
            models.Index(fields=['project', 'version_number']),
        ]

    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid.uuid4().hex[:16]
        if self.commit_message:
            self.commit_message = sanitize_text(self.commit_message)
        if self.hash:
            self.hash = sanitize_text(self.hash)
        super().save(*args, **kwargs)
    
    def __str__(self):
        creator = self.created_by.username if self.created_by else 'Unknown'
        storage_type = 'Snapshot' if self.is_snapshot else 'CAS'
        version_display = f"v{self.version_number}" if self.version_number else f"UID:{self.uid[:8]}"
        return f"{self.project} - {version_display} by {creator} ({storage_type}) [{self.status}]"
    
    def assign_version_number(self):
        """Assign version number based on project's completed versions"""
        if self.version_number:
            return self.version_number
        
        completed_versions = Version.objects.filter(
            project=self.project,
            status='completed'
        ).exclude(uid=self.uid)
        
        self.version_number = completed_versions.count() + 1
        self.save(update_fields=['version_number'])
        return self.version_number
    
    def get_file_size_mb(self):
        """Get file size in megabytes"""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0
    
    def get_size_change_mb(self):
        """Get size change in megabytes"""
        if self.size_change:
            return round(self.size_change / (1024 * 1024), 2)
        return 0
    
    def get_storage_type(self):
        """Get storage type for display"""
        return 'Full Snapshot' if self.is_snapshot else 'CAS Manifest'
    
    def is_ready(self):
        """Check if version is completed and ready for use"""
        return self.status == 'completed'
    
    def mark_completed(self):
        """Mark version as completed and assign version number"""
        from django.utils import timezone
        self.status = 'completed'
        self.completed_at = timezone.now()
        
        # Assign version number if not already assigned
        if not self.version_number:
            self.assign_version_number()
        
        self.save(update_fields=['status', 'completed_at', 'version_number'])
    
    def mark_failed(self):
        """Mark version as failed"""
        from django.utils import timezone
        self.status = 'failed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at'])
    
    def get_version_directory(self):
        """Get the storage directory for this version"""
        if self.version_number:
            return get_version_storage_path(
                self.project.owner.username,
                self.project.name,
                self.version_number
            )
        # Fallback for temp versions
        return os.path.join(
            get_project_storage_path(
                self.project.owner.username,
                self.project.name
            ),
            'versions',
            f'temp_{self.uid}'
        )
    
    def save_manifest_to_file(self, manifest_dict):
        """Save manifest dictionary to file"""
        version_dir = self.get_version_directory()
        os.makedirs(version_dir, exist_ok=True)
        
        manifest_file = os.path.join(version_dir, 'manifest.json')
        
        try:
            with open(manifest_file, 'w', encoding='utf-8') as f:
                json.dump(manifest_dict, f, indent=2, ensure_ascii=False)
            
            relative_path = os.path.relpath(manifest_file, settings.MEDIA_ROOT)
            self.manifest_file_path = relative_path
            self.save(update_fields=['manifest_file_path'])
            
            print(f"[MANIFEST] Saved to {manifest_file}")
            return manifest_file
        
        except Exception as e:
            print(f"[ERROR] Manifest save failed: {e}")
            raise
    
    def load_manifest_from_file(self):
        """Load manifest from file"""
        if not self.manifest_file_path:
            return None
        
        manifest_file = os.path.join(settings.MEDIA_ROOT, self.manifest_file_path)
        
        if not os.path.exists(manifest_file):
            return None
        
        try:
            with open(manifest_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[ERROR] Manifest load failed: {e}")
            return None
    
    def get_change_summary(self):
        """Get detailed change summary"""
        if not self.previous_version:
            return {
                'is_initial': True,
                'files_added': self.file_count,
                'files_modified': 0,
                'files_deleted': 0,
                'size_change_mb': self.get_file_size_mb(),
                'added_files': [],
                'modified_files': [],
                'deleted_files': []
            }
        
        return {
            'is_initial': False,
            'files_added': self.files_added,
            'files_modified': self.files_modified,
            'files_deleted': self.files_deleted,
            'size_change_mb': self.get_size_change_mb(),
            'previous_version_number': self.previous_version.version_number,
            'added_files': self.change_details.get('added_files', []),
            'modified_files': self.change_details.get('modified_files', []),
            'deleted_files': self.change_details.get('deleted_files', [])
        }


@receiver(pre_delete, sender=Version)
def version_pre_delete(sender, instance, **kwargs):
    """Clean up version files and decrement blob references"""
    print(f"\n[VERSION CLEANUP] Starting cleanup for version {instance.uid}")
    
    # Delete snapshot file
    if instance.file and instance.is_snapshot:
        try:
            file_path = instance.file.path
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"[VERSION] Deleted snapshot: {file_path}")
        except Exception as e:
            print(f"[VERSION ERROR] Snapshot deletion failed: {e}")
    
    # Decrement blob references for CAS versions
    manifest = instance.load_manifest_from_file()
    if manifest and isinstance(manifest, dict):
        files = manifest.get('files', [])
        blob_ids = set()
        
        for file_info in files:
            if file_info.get('storage') == 'cas':
                blob_id = file_info.get('blob_id')
                if blob_id:
                    blob_ids.add(blob_id)
        
        print(f"[VERSION] Decrementing references for {len(blob_ids)} blobs")
        
        for blob_id in blob_ids:
            try:
                blob = FileBlob.objects.get(id=blob_id)
                blob.decrement_ref()
                print(f"[BLOB] Decremented ref for blob {blob.hash[:16]}... (refs: {blob.ref_count})")
            except FileBlob.DoesNotExist:
                print(f"[BLOB WARNING] Blob {blob_id} not found")


@receiver(post_delete, sender=Version)
def version_post_delete(sender, instance, **kwargs):
    """Clean up version directory after deletion"""
    try:
        version_dir = instance.get_version_directory()
        if os.path.exists(version_dir):
            shutil.rmtree(version_dir, ignore_errors=True)
            print(f"[VERSION] Deleted directory: {version_dir}")
            
            versions_dir = os.path.dirname(version_dir)
            if os.path.exists(versions_dir) and not os.listdir(versions_dir):
                os.rmdir(versions_dir)
                print(f"[VERSION] Removed empty versions directory")
    except Exception as e:
        print(f"[VERSION ERROR] Directory cleanup failed: {e}")


class DownloadRequest(models.Model):
    """Download request with UUID and expiration"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('expired', 'Expired'),
    ]
    
    EXPIRATION_HOURS = 1
    
    uid = models.CharField(max_length=16, unique=True, db_index=True, editable=False)
    
    version = models.ForeignKey(
        Version,
        on_delete=models.CASCADE,
        related_name='download_requests'
    )
    requested_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='download_requests'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    message = models.TextField(null=True, blank=True)
    
    zip_file = models.FileField(upload_to=download_zip_path, null=True, blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    
    error_details = models.TextField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        db_table = 'versions_downloadrequest'
        indexes = [
            models.Index(fields=['uid']),
            models.Index(fields=['version', '-created_at']),
            models.Index(fields=['status']),
            models.Index(fields=['expires_at']),
        ]
    
    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid.uuid4().hex[:16]
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Download {self.uid} - v{self.version.version_number} by {self.requested_by.username} [{self.status}]"
    
    def mark_completed(self, zip_path, file_size):
        """Mark download as completed"""
        from django.utils import timezone
        from datetime import timedelta
        from django.core.files import File
        
        self.status = 'completed'
        self.progress = 100
        self.completed_at = timezone.now()
        self.expires_at = timezone.now() + timedelta(hours=self.EXPIRATION_HOURS)
        self.file_size = file_size
        
        with open(zip_path, 'rb') as f:
            self.zip_file.save(os.path.basename(zip_path), File(f), save=False)
        
        self.save()
    
    def mark_failed(self, error_message):
        """Mark download as failed"""
        from django.utils import timezone
        self.status = 'failed'
        self.progress = 100
        self.completed_at = timezone.now()
        self.error_details = sanitize_text(error_message)
        self.save()
    
    def is_expired(self):
        """Check if download has expired"""
        from django.utils import timezone
        if self.expires_at and self.expires_at < timezone.now():
            return True
        return False
    
    def get_time_remaining_seconds(self):
        """Get time remaining in seconds"""
        from django.utils import timezone
        if self.expires_at and self.status == 'completed':
            remaining = (self.expires_at - timezone.now()).total_seconds()
            return max(0, int(remaining))
        return 0
    
    def get_time_remaining_formatted(self):
        """Get formatted time remaining"""
        seconds = self.get_time_remaining_seconds()
        
        if seconds <= 0:
            return "Expired"
        
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        
        if hours > 0:
            return f"{int(hours)}h {int(minutes)}m"
        elif minutes > 0:
            return f"{int(minutes)}m"
        else:
            return f"{int(seconds)}s"
    
    def get_download_url(self):
        """Get download URL if available"""
        if self.zip_file and self.status == 'completed' and not self.is_expired():
            return self.zip_file.url
        return None


@receiver(pre_delete, sender=DownloadRequest)
def download_request_pre_delete(sender, instance, **kwargs):
    """Delete ZIP file before model deletion"""
    if instance.zip_file:
        try:
            file_path = instance.zip_file.path
            if os.path.isfile(file_path):
                os.remove(file_path)
                print(f"[DOWNLOAD] Deleted ZIP: {file_path}")
        except Exception as e:
            print(f"[DOWNLOAD ERROR] ZIP deletion failed: {e}")


class PendingPush(models.Model):
    """Push request with UUID and approval workflow"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('approved', 'Approved'),
        ('processing', 'Processing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected'),
        ('cancelled', 'Cancelled')
    ]
    
    uid = models.CharField(max_length=16, unique=True, db_index=True, editable=False)
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='pushes_new'
    )
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='pushes_created_new'
    )
    commit_message = models.TextField()
    file_list = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    approved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='pushes_approved_new'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    
    version = models.ForeignKey(
        Version,
        on_delete=models.SET_NULL,
        null=True,
        blank=True
    )
    error_details = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pending Push (New)'
        verbose_name_plural = 'Pending Pushes (New)'
        db_table = 'versions_pendingpush'
        indexes = [
            models.Index(fields=['uid']),
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['status']),
        ]

    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid.uuid4().hex[:16]
        if self.commit_message:
            self.commit_message = sanitize_text(self.commit_message)
        if self.message:
            self.message = sanitize_text(self.message)
        if self.error_details:
            self.error_details = sanitize_text(self.error_details)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Push {self.uid} by {self.created_by.username} - {self.project} - {self.status}"
    
    def is_active(self):
        """Check if push is currently active"""
        return self.status in [
            'pending', 'awaiting_approval', 'approved', 'processing'
        ]
    
    def mark_completed(self):
        """Mark push as completed"""
        from django.utils import timezone
        self.status = 'done'
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message=None):
        """Mark push as failed"""
        from django.utils import timezone
        self.status = 'failed'
        self.progress = 100
        self.completed_at = timezone.now()
        if error_message:
            self.error_details = sanitize_text(error_message)
        self.save()
        
        if self.version:
            try:
                self.version.mark_failed()
            except Exception as e:
                print(f"[ERROR] Version mark failed: {e}")
    
    def cancel(self):
        """Cancel push"""
        from django.utils import timezone
        self.status = 'cancelled'
        self.message = 'Cancelled by user'
        self.progress = 100
        self.completed_at = timezone.now()
        self.save()
        
        if self.version:
            try:
                self.version.delete()
            except Exception as e:
                print(f"[ERROR] Version deletion on cancel failed: {e}")
    
    def approve(self, approver):
        """Approve push"""
        from django.utils import timezone
        self.status = 'approved'
        self.approved_by = approver
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self, rejector, reason=None):
        """Reject push"""
        from django.utils import timezone
        self.status = 'rejected'
        self.approved_by = rejector
        self.approved_at = timezone.now()
        self.rejection_reason = sanitize_text(reason) if reason else None
        self.completed_at = timezone.now()
        self.save()
        
        if self.version:
            try:
                self.version.delete()
            except Exception as e:
                print(f"[ERROR] Version deletion on reject failed: {e}")