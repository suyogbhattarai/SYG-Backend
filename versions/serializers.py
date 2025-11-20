"""
=============================================================================
FILE 3: versions/serializers.py
=============================================================================
Serializers for version control with file-based manifest storage
Updated to properly display snapshot vs CAS information
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Version, PendingPush, FileBlob, DownloadRequest


class FileBlobSerializer(serializers.ModelSerializer):
    """File blob information"""
    size_mb = serializers.SerializerMethodField()
    
    class Meta:
        model = FileBlob
        fields = ['id', 'hash', 'size', 'size_mb', 'ref_count', 'created_at']
        read_only_fields = ['created_at', 'ref_count']
    
    def get_size_mb(self, obj):
        return obj.get_size_mb()


class VersionSerializer(serializers.ModelSerializer):
    """Version with creator information and storage details"""
    version_number = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    storage_type = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    manifest_summary = serializers.SerializerMethodField()
    is_ready = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Version
        fields = [
            'id', 'project', 'project_name',
            'version_number', 'commit_message',
            'status', 'status_display', 'is_ready',
            'is_snapshot', 'storage_type',
            'file', 'file_url', 'file_size', 'file_size_mb', 'file_count',
            'manifest_summary',
            'hash', 'created_at', 'completed_at',
            'created_by', 'created_by_username'
        ]
        read_only_fields = ['created_at', 'completed_at', 'hash', 'created_by', 'is_snapshot', 'status']
    
    def get_version_number(self, obj):
        """Get version number for completed versions only"""
        if obj.status == 'completed':
            return obj.get_version_number()
        return None
    
    def get_file_size_mb(self, obj):
        """Get file size in MB"""
        return obj.get_file_size_mb()
    
    def get_file_url(self, obj):
        """Get file URL for snapshot versions"""
        if obj.file and obj.is_snapshot and obj.status == 'completed':
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    
    def get_storage_type(self, obj):
        """Get storage type for display"""
        return obj.get_storage_type()
    
    def get_is_ready(self, obj):
        """Check if version is ready for use"""
        return obj.is_ready()
    
    def get_manifest_summary(self, obj):
        """Get summary of manifest WITHOUT loading entire file"""
        if obj.is_snapshot:
            return {
                'type': 'snapshot',
                'message': 'Full ZIP snapshot - no manifest'
            }
        
        # Load manifest summary efficiently for CAS versions
        return obj.get_manifest_summary()


class VersionListSerializer(serializers.ModelSerializer):
    """Lightweight version list serializer with status indicators"""
    version_number = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    storage_type = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    is_ready = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = Version
        fields = [
            'id', 'version_number', 'commit_message',
            'status', 'status_display', 'is_ready',
            'is_snapshot', 'storage_type',
            'file_size_mb', 'file_count', 
            'created_at', 'completed_at',
            'created_by_username'
        ]
    
    def get_version_number(self, obj):
        """Get version number for completed versions only"""
        if obj.status == 'completed':
            return obj.get_version_number()
        return None
    
    def get_file_size_mb(self, obj):
        """Get file size in MB"""
        return obj.get_file_size_mb()
    
    def get_storage_type(self, obj):
        """Get storage type"""
        return 'Snapshot' if obj.is_snapshot else 'CAS'
    
    def get_is_ready(self, obj):
        """Check if version is ready for use"""
        return obj.is_ready()


class DownloadRequestSerializer(serializers.ModelSerializer):
    """Download request with progress tracking"""
    version_number = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='version.project.name', read_only=True)
    requested_by_username = serializers.CharField(source='requested_by.username', read_only=True)
    download_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    time_remaining = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = DownloadRequest
        fields = [
            'id', 'version', 'version_number', 'project_name',
            'requested_by', 'requested_by_username',
            'status', 'status_display', 'progress', 'message',
            'download_url', 'file_size', 'file_size_mb',
            'created_at', 'completed_at', 'expires_at',
            'is_expired', 'time_remaining',
            'error_details'
        ]
        read_only_fields = [
            'status', 'progress', 'message', 'download_url',
            'file_size', 'created_at', 'completed_at', 'expires_at',
            'error_details'
        ]
    
    def get_version_number(self, obj):
        """Get version number"""
        return obj.version.get_version_number()
    
    def get_download_url(self, obj):
        """Get download URL if available"""
        if obj.status == 'completed' and not obj.is_expired():
            request = self.context.get('request')
            if request and obj.zip_file:
                return request.build_absolute_uri(obj.zip_file.url)
            return obj.get_download_url()
        return None
    
    def get_file_size_mb(self, obj):
        """Get file size in MB"""
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return None
    
    def get_is_expired(self, obj):
        """Check if download has expired"""
        return obj.is_expired()
    
    def get_time_remaining(self, obj):
        """Get time remaining until expiration in hours"""
        from django.utils import timezone
        if obj.expires_at and obj.status == 'completed':
            remaining = (obj.expires_at - timezone.now()).total_seconds() / 3600
            if remaining > 0:
                return round(remaining, 1)
        return None


class PendingPushSerializer(serializers.ModelSerializer):
    """Push request with approval workflow"""
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True, allow_null=True)
    is_active = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    version_number = serializers.SerializerMethodField()
    version_status = serializers.SerializerMethodField()
    requires_approval = serializers.SerializerMethodField()
    
    class Meta:
        model = PendingPush
        fields = [
            'id', 'project', 'project_name',
            'commit_message', 'file_list',
            'status', 'progress', 'message', 'error_details',
            'is_active', 'duration',
            'created_at', 'completed_at',
            'created_by', 'created_by_username',
            'approved_by', 'approved_by_username', 'approved_at',
            'rejection_reason',
            'version', 'version_number', 'version_status',
            'requires_approval'
        ]
        read_only_fields = [
            'status', 'progress', 'message',
            'created_at', 'completed_at', 'created_by',
            'approved_by', 'approved_at'
        ]
    
    def get_is_active(self, obj):
        """Check if push is active"""
        return obj.is_active()
    
    def get_duration(self, obj):
        """Get push duration in seconds"""
        from django.utils import timezone
        end_time = obj.completed_at or timezone.now()
        duration = (end_time - obj.created_at).total_seconds()
        return round(duration, 2)
    
    def get_version_number(self, obj):
        """Get version number if available"""
        if obj.version and obj.version.status == 'completed':
            return obj.version.get_version_number()
        return None
    
    def get_version_status(self, obj):
        """Get version status"""
        if obj.version:
            return obj.version.status
        return None
    
    def get_requires_approval(self, obj):
        """Check if this push requires approval"""
        return (
            obj.project.require_push_approval and
            obj.created_by != obj.project.owner
        )


class VersionUploadSerializer(serializers.Serializer):
    """Serializer for version upload from plugin"""
    project_name = serializers.CharField(max_length=255)
    commit_message = serializers.CharField(required=False, default='Version from DAW plugin')
    file_list = serializers.ListField(child=serializers.DictField())
    
    def validate_file_list(self, value):
        """Validate file list structure"""
        if not isinstance(value, list):
            raise serializers.ValidationError("file_list must be an array")
        
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each file entry must be an object")
            
            if 'relative_path' not in item:
                raise serializers.ValidationError("Each file must have a relative_path")
        
        return value