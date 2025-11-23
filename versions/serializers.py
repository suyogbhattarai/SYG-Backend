"""
versions/serializers.py
FIXED: UUID support, detailed change tracking, and blob reference info
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Version, PendingPush, FileBlob, DownloadRequest, BlobReference


class FileBlobSerializer(serializers.ModelSerializer):
    """File blob information"""
    size_mb = serializers.SerializerMethodField()
    reference_count = serializers.SerializerMethodField()
    referenced_by_projects = serializers.SerializerMethodField()
    
    class Meta:
        model = FileBlob
        fields = ['id', 'hash', 'size', 'size_mb', 'ref_count', 'reference_count', 'referenced_by_projects', 'created_at']
        read_only_fields = ['created_at', 'ref_count', 'reference_count', 'referenced_by_projects']
    
    def get_size_mb(self, obj):
        return obj.get_size_mb()
    
    def get_reference_count(self, obj):
        """Get actual count of active references"""
        return obj.get_reference_count()
    
    def get_referenced_by_projects(self, obj):
        """Get list of projects that reference this blob"""
        refs = BlobReference.objects.filter(blob=obj).distinct('project')
        return [ref.project.name for ref in refs]


class VersionSerializer(serializers.ModelSerializer):
    """Version with detailed change information"""
    uid = serializers.CharField(read_only=True)
    version_number = serializers.IntegerField(read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    storage_type = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_uid = serializers.CharField(source='project.uid', read_only=True)
    project_id = serializers.IntegerField(source='project.id', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    manifest_summary = serializers.SerializerMethodField()
    is_ready = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    # Detailed change tracking
    change_summary = serializers.SerializerMethodField()
    size_change_mb = serializers.SerializerMethodField()
    previous_version_number = serializers.SerializerMethodField()
    
    class Meta:
        model = Version
        fields = [
            'uid', 'id', 'project', 'project_name', 'project_uid', 'project_id',
            'version_number', 'commit_message',
            'status', 'status_display', 'is_ready',
            'is_snapshot', 'storage_type',
            'file', 'file_url', 'file_size', 'file_size_mb', 'file_count',
            'manifest_summary',
            'hash', 'created_at', 'completed_at',
            'created_by', 'created_by_username',
            # Change tracking
            'files_added', 'files_modified', 'files_deleted', 
            'size_change', 'size_change_mb',
            'previous_version', 'previous_version_number',
            'change_summary'
        ]
        read_only_fields = [
            'uid', 'created_at', 'completed_at', 'hash', 'created_by', 
            'is_snapshot', 'status', 'files_added', 'files_modified', 
            'files_deleted', 'size_change', 'previous_version', 'version_number'
        ]
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
    
    def get_size_change_mb(self, obj):
        return obj.get_size_change_mb()
    
    def get_previous_version_number(self, obj):
        if obj.previous_version and obj.previous_version.version_number:
            return obj.previous_version.version_number
        return None
    
    def get_file_url(self, obj):
        if obj.file and obj.is_snapshot and obj.status == 'completed':
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None
    
    def get_storage_type(self, obj):
        return obj.get_storage_type()
    
    def get_is_ready(self, obj):
        return obj.is_ready()
    
    def get_manifest_summary(self, obj):
        if obj.is_snapshot:
            return {
                'type': 'snapshot',
                'message': 'Full ZIP snapshot'
            }
        
        manifest = obj.load_manifest_from_file()
        if not manifest:
            return {
                'type': 'cas',
                'message': 'Manifest not available'
            }
        
        files = manifest.get('files', [])
        cas_files = [f for f in files if f.get('storage') == 'cas']
        inline_files = [f for f in files if f.get('storage') == 'inline']
        
        return {
            'type': 'cas',
            'total_files': len(files),
            'cas_files': len(cas_files),
            'inline_files': len(inline_files),
            'cas_threshold_mb': manifest.get('cas_threshold_mb')
        }
    
    def get_change_summary(self, obj):
        """Get detailed change summary with file names"""
        summary = obj.get_change_summary()
        
        # Limit number of files shown to prevent huge responses
        max_files = 50
        
        if summary.get('added_files'):
            summary['added_files'] = summary['added_files'][:max_files]
            if len(summary.get('added_files', [])) >= max_files:
                summary['added_files_truncated'] = True
        
        if summary.get('modified_files'):
            summary['modified_files'] = summary['modified_files'][:max_files]
            if len(summary.get('modified_files', [])) >= max_files:
                summary['modified_files_truncated'] = True
        
        if summary.get('deleted_files'):
            summary['deleted_files'] = summary['deleted_files'][:max_files]
            if len(summary.get('deleted_files', [])) >= max_files:
                summary['deleted_files_truncated'] = True
        
        return summary


class VersionListSerializer(serializers.ModelSerializer):
    """Lightweight version list with change summary"""
    uid = serializers.CharField(read_only=True)
    version_number = serializers.IntegerField(read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    storage_type = serializers.SerializerMethodField()
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    is_ready = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    size_change_mb = serializers.SerializerMethodField()
    has_changes = serializers.SerializerMethodField()
    
    class Meta:
        model = Version
        fields = [
            'uid', 'id', 'version_number', 'commit_message',
            'status', 'status_display', 'is_ready',
            'is_snapshot', 'storage_type',
            'file_size_mb', 'file_count', 
            'created_at', 'completed_at',
            'created_by_username',
            'files_added', 'files_modified', 'files_deleted',
            'size_change_mb', 'has_changes'
        ]
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
    
    def get_size_change_mb(self, obj):
        return obj.get_size_change_mb()
    
    def get_storage_type(self, obj):
        return 'Snapshot' if obj.is_snapshot else 'CAS'
    
    def get_is_ready(self, obj):
        return obj.is_ready()
    
    def get_has_changes(self, obj):
        return (obj.files_added + obj.files_modified + obj.files_deleted) > 0


class DownloadRequestSerializer(serializers.ModelSerializer):
    """Download request with UID"""
    uid = serializers.CharField(read_only=True)
    version_number = serializers.SerializerMethodField()
    version_uid = serializers.CharField(source='version.uid', read_only=True)
    project_name = serializers.CharField(source='version.project.name', read_only=True)
    project_uid = serializers.CharField(source='version.project.uid', read_only=True)
    project_id = serializers.IntegerField(source='version.project.id', read_only=True)
    requested_by_username = serializers.CharField(source='requested_by.username', read_only=True)
    download_url = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    is_expired = serializers.SerializerMethodField()
    time_remaining_seconds = serializers.SerializerMethodField()
    time_remaining_formatted = serializers.SerializerMethodField()
    expiration_hours = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    
    class Meta:
        model = DownloadRequest
        fields = [
            'uid', 'id', 'version', 'version_uid', 'version_number', 
            'project_name', 'project_uid', 'project_id',
            'requested_by', 'requested_by_username',
            'status', 'status_display', 'progress', 'message',
            'download_url', 'file_size', 'file_size_mb',
            'created_at', 'completed_at', 'expires_at',
            'is_expired', 'time_remaining_seconds', 'time_remaining_formatted',
            'expiration_hours',
            'error_details'
        ]
        read_only_fields = [
            'uid', 'status', 'progress', 'message', 'download_url',
            'file_size', 'created_at', 'completed_at', 'expires_at',
            'error_details'
        ]
    
    def get_version_number(self, obj):
        return obj.version.version_number
    
    def get_download_url(self, obj):
        if obj.status == 'completed' and not obj.is_expired():
            request = self.context.get('request')
            if request and obj.zip_file:
                return request.build_absolute_uri(obj.zip_file.url)
            return obj.get_download_url()
        return None
    
    def get_file_size_mb(self, obj):
        if obj.file_size:
            return round(obj.file_size / (1024 * 1024), 2)
        return None
    
    def get_is_expired(self, obj):
        return obj.is_expired()
    
    def get_time_remaining_seconds(self, obj):
        return obj.get_time_remaining_seconds()
    
    def get_time_remaining_formatted(self, obj):
        return obj.get_time_remaining_formatted()
    
    def get_expiration_hours(self, obj):
        return obj.EXPIRATION_HOURS


class PendingPushSerializer(serializers.ModelSerializer):
    """Push request with UID"""
    uid = serializers.CharField(read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    project_uid = serializers.CharField(source='project.uid', read_only=True)
    project_id = serializers.IntegerField(source='project.id', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True, allow_null=True)
    is_active = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    version_number = serializers.SerializerMethodField()
    version_uid = serializers.SerializerMethodField()
    version_status = serializers.SerializerMethodField()
    requires_approval = serializers.SerializerMethodField()
    
    class Meta:
        model = PendingPush
        fields = [
            'uid', 'id', 'project', 'project_uid', 'project_id', 'project_name',
            'commit_message', 'file_list',
            'status', 'progress', 'message', 'error_details',
            'is_active', 'duration',
            'created_at', 'completed_at',
            'created_by', 'created_by_username',
            'approved_by', 'approved_by_username', 'approved_at',
            'rejection_reason',
            'version', 'version_uid', 'version_number', 'version_status',
            'requires_approval'
        ]
        read_only_fields = [
            'uid', 'status', 'progress', 'message',
            'created_at', 'completed_at', 'created_by',
            'approved_by', 'approved_at'
        ]
    
    def get_is_active(self, obj):
        return obj.is_active()
    
    def get_duration(self, obj):
        from django.utils import timezone
        end_time = obj.completed_at or timezone.now()
        duration = (end_time - obj.created_at).total_seconds()
        return round(duration, 2)
    
    def get_version_number(self, obj):
        if obj.version and obj.version.version_number:
            return obj.version.version_number
        return None
    
    def get_version_uid(self, obj):
        if obj.version:
            return obj.version.uid
        return None
    
    def get_version_status(self, obj):
        if obj.version:
            return obj.version.status
        return None
    
    def get_requires_approval(self, obj):
        return (
            obj.project.require_push_approval and
            obj.created_by != obj.project.owner
        )


class VersionUploadSerializer(serializers.Serializer):
    """Version upload from plugin"""
    project_name = serializers.CharField(max_length=255)
    commit_message = serializers.CharField(required=False, default='Version from DAW plugin')
    file_list = serializers.ListField(child=serializers.DictField())
    
    def validate_file_list(self, value):
        if not isinstance(value, list):
            raise serializers.ValidationError("file_list must be an array")
        
        for item in value:
            if not isinstance(item, dict):
                raise serializers.ValidationError("Each file entry must be an object")
            
            if 'relative_path' not in item:
                raise serializers.ValidationError("Each file must have a relative_path")
        
        return value