# versioning/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    UserProfile, Project, ProjectMember, Version, 
    PendingPush, ActivityLog, SampleBasket
)

class UserSerializer(serializers.ModelSerializer):
    """Basic user information"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class UserProfileSerializer(serializers.ModelSerializer):
    """User profile with API key"""
    user = UserSerializer(read_only=True)
    
    class Meta:
        model = UserProfile
        fields = ['user', 'api_key', 'created_at']
        read_only_fields = ['api_key', 'created_at']


class ProjectMemberSerializer(serializers.ModelSerializer):
    """Project member with user details"""
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True)
    added_by_username = serializers.CharField(source='added_by.username', read_only=True)
    
    class Meta:
        model = ProjectMember
        fields = [
            'id', 'user', 'user_id', 'role', 
            'added_at', 'added_by_username'
        ]
        read_only_fields = ['id', 'added_at']
    
    def validate_user_id(self, value):
        """Ensure user exists"""
        try:
            User.objects.get(id=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User does not exist")
        return value


class ProjectSerializer(serializers.ModelSerializer):
    """Full project details with team and stats"""
    owner = UserSerializer(read_only=True)
    version_count = serializers.SerializerMethodField()
    has_active_push = serializers.SerializerMethodField()
    latest_version = serializers.SerializerMethodField()
    members = ProjectMemberSerializer(many=True, read_only=True)
    user_role = serializers.SerializerMethodField()
    sample_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'owner',
            'created_at', 'updated_at',
            'version_count', 'has_active_push', 'latest_version',
            'members', 'user_role',
            'require_push_approval', 'ignore_patterns',
            'sample_count'
        ]
        read_only_fields = ['created_at', 'updated_at', 'owner']
    
    def get_version_count(self, obj):
        return obj.versions.count()
    
    def get_has_active_push(self, obj):
        return obj.pendingpush_set.filter(
            status__in=['pending', 'processing', 'zipping', 'comparing', 'awaiting_approval']
        ).exists()
    
    def get_latest_version(self, obj):
        latest = obj.versions.order_by('-created_at').first()
        if latest:
            return {
                'id': latest.id,
                'version_number': latest.get_version_number(),
                'commit_message': latest.commit_message,
                'created_at': latest.created_at,
                'created_by': latest.created_by.username if latest.created_by else None,
                'file_size_mb': latest.get_file_size_mb()
            }
        return None
    
    def get_user_role(self, obj):
        """Get current user's role in the project"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_user_role(request.user)
        return None
    
    def get_sample_count(self, obj):
        return obj.samples.count()


class VersionSerializer(serializers.ModelSerializer):
    """Version with creator information"""
    version_number = serializers.SerializerMethodField()
    file_size_mb = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    
    class Meta:
        model = Version
        fields = [
            'id', 'project', 'project_name',
            'version_number', 'commit_message',
            'file', 'file_url', 'file_size', 'file_size_mb', 'file_count',
            'hash', 'created_at',
            'created_by', 'created_by_username'
        ]
        read_only_fields = ['created_at', 'hash', 'created_by']
    
    def get_version_number(self, obj):
        return obj.get_version_number()
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class PendingPushSerializer(serializers.ModelSerializer):
    """Push request with approval workflow"""
    project_name = serializers.CharField(source='project.name', read_only=True)
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    approved_by_username = serializers.CharField(source='approved_by.username', read_only=True)
    is_active = serializers.SerializerMethodField()
    duration = serializers.SerializerMethodField()
    version_number = serializers.SerializerMethodField()
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
            'version', 'version_number',
            'requires_approval'
        ]
        read_only_fields = [
            'status', 'progress', 'message', 
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
        if obj.version:
            return obj.version.get_version_number()
        return None
    
    def get_requires_approval(self, obj):
        """Check if this push requires approval"""
        return (
            obj.project.require_push_approval and 
            obj.created_by != obj.project.owner
        )


class ActivityLogSerializer(serializers.ModelSerializer):
    """Activity log entry"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = [
            'id', 'project', 'project_name',
            'user', 'user_username',
            'action', 'description', 'metadata',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SampleBasketSerializer(serializers.ModelSerializer):
    """Sample file in project basket"""
    uploaded_by_username = serializers.CharField(source='uploaded_by.username', read_only=True)
    file_size_mb = serializers.SerializerMethodField()
    file_url = serializers.SerializerMethodField()
    
    class Meta:
        model = SampleBasket
        fields = [
            'id', 'project', 'name', 'description',
            'file', 'file_url', 'file_size', 'file_size_mb', 'file_type',
            'tags', 'uploaded_at',
            'uploaded_by', 'uploaded_by_username'
        ]
        read_only_fields = ['id', 'uploaded_at', 'uploaded_by', 'file_size']
    
    def get_file_size_mb(self, obj):
        return obj.get_file_size_mb()
    
    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class ProjectStatusSerializer(serializers.ModelSerializer):
    """Optimized for repository tab polling"""
    version_count = serializers.IntegerField(read_only=True)
    has_active_push = serializers.SerializerMethodField()
    latest_push = serializers.SerializerMethodField()
    active_pushes = serializers.SerializerMethodField()
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    user_role = serializers.SerializerMethodField()
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'owner_username',
            'version_count', 'created_at',
            'has_active_push', 'latest_push', 'active_pushes',
            'user_role'
        ]
    
    def get_has_active_push(self, obj):
        return getattr(obj, 'has_active', False)
    
    def get_latest_push(self, obj):
        latest = obj.pendingpush_set.order_by('-created_at').first()
        if latest:
            return {
                'push_id': latest.id,
                'status': latest.status,
                'progress': latest.progress,
                'message': latest.message or '',
                'created_at': latest.created_at,
                'created_by': latest.created_by.username if latest.created_by else None
            }
        return None
    
    def get_active_pushes(self, obj):
        active = obj.pendingpush_set.filter(
            status__in=['pending', 'processing', 'zipping', 'comparing', 'awaiting_approval']
        ).order_by('-created_at')
        
        return [
            {
                'push_id': push.id,
                'status': push.status,
                'progress': push.progress,
                'message': push.message or '',
                'created_at': push.created_at,
                'created_by': push.created_by.username if push.created_by else None
            }
            for push in active
        ]
    
    def get_user_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_user_role(request.user)
        return None