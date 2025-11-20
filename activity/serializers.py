# activity/serializers.py
"""
Serializers for activity logs
"""

from rest_framework import serializers
from .models import ActivityLog


class ActivityLogSerializer(serializers.ModelSerializer):
    """Activity log entry"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    user_full_name = serializers.SerializerMethodField()
    project_name = serializers.CharField(source='project.name', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = [
            'id', 'project', 'project_name',
            'user', 'user_username', 'user_full_name',
            'action', 'action_display', 'description', 'metadata',
            'created_at'
        ]
        read_only_fields = ['id', 'created_at']
    
    def get_user_full_name(self, obj):
        if obj.user:
            full_name = f"{obj.user.first_name} {obj.user.last_name}".strip()
            return full_name if full_name else obj.user.username
        return 'System'


class ActivityLogListSerializer(serializers.ModelSerializer):
    """Lightweight activity log serializer for lists"""
    user_username = serializers.CharField(source='user.username', read_only=True)
    action_display = serializers.CharField(source='get_action_display', read_only=True)
    
    class Meta:
        model = ActivityLog
        fields = [
            'id', 'action', 'action_display', 'description',
            'user_username', 'created_at'
        ]