# projects/serializers.py
"""
Serializers for projects and team management
"""

from rest_framework import serializers
from django.contrib.auth.models import User
from .models import Project, ProjectMember


class UserSerializer(serializers.ModelSerializer):
    """Basic user information"""
    class Meta:
        model = User
        fields = ['id', 'username', 'email', 'first_name', 'last_name']
        read_only_fields = ['id']


class ProjectMemberSerializer(serializers.ModelSerializer):
    """Project member with user details"""
    user = UserSerializer(read_only=True)
    user_id = serializers.IntegerField(write_only=True, required=False)
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
    members = ProjectMemberSerializer(many=True, read_only=True, source='members_new')
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
        return obj.get_version_count()
    
    def get_has_active_push(self, obj):
        return obj.has_active_push()
    
    def get_latest_version(self, obj):
        latest = obj.get_latest_version()
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
        return obj.samples_new.count() if hasattr(obj, 'samples_new') else 0


class ProjectListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for project lists"""
    owner = UserSerializer(read_only=True)
    version_count = serializers.SerializerMethodField()
    has_active_push = serializers.SerializerMethodField()
    user_role = serializers.SerializerMethodField()
    
    class Meta:
        model = Project
        fields = [
            'id', 'name', 'description', 'owner',
            'created_at', 'updated_at',
            'version_count', 'has_active_push', 'user_role',
            'require_push_approval'
        ]
        read_only_fields = ['created_at', 'updated_at', 'owner']
    
    def get_version_count(self, obj):
        return obj.get_version_count()
    
    def get_has_active_push(self, obj):
        return obj.has_active_push()
    
    def get_user_role(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return obj.get_user_role(request.user)
        return None


class ProjectCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating projects"""
    class Meta:
        model = Project
        fields = ['name', 'description', 'require_push_approval', 'ignore_patterns']
    
    def validate_name(self, value):
        """Ensure project name is unique for the user"""
        request = self.context.get('request')
        if request and request.user:
            if Project.objects.filter(owner=request.user, name=value).exists():
                raise serializers.ValidationError(
                    "You already have a project with this name"
                )
        return value


class ProjectUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating projects"""
    class Meta:
        model = Project
        fields = ['name', 'description', 'require_push_approval', 'ignore_patterns']
    
    def validate_name(self, value):
        """Ensure project name is unique for the user"""
        request = self.context.get('request')
        instance = self.instance
        
        if request and request.user:
            # Exclude current project from check
            if Project.objects.filter(
                owner=request.user,
                name=value
            ).exclude(id=instance.id).exists():
                raise serializers.ValidationError(
                    "You already have a project with this name"
                )
        return value


class ProjectStatusSerializer(serializers.ModelSerializer):
    """Optimized for repository tab polling"""
    version_count = serializers.SerializerMethodField()
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
    
    def get_version_count(self, obj):
        return obj.get_version_count()
    
    def get_has_active_push(self, obj):
        return obj.has_active_push()
    
    def get_latest_push(self, obj):
        latest = obj.pushes_new.order_by('-created_at').first() if hasattr(obj, 'pushes_new') else None
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
        if not hasattr(obj, 'pushes_new'):
            return []
        
        active = obj.pushes_new.filter(
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