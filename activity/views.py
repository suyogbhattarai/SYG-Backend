# activity/views.py
"""
Activity log views
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404

from projects.models import Project
from projects.permissions import CanViewProject
from .models import ActivityLog
from .serializers import ActivityLogSerializer, ActivityLogListSerializer


def sanitize_string(s):
    """Remove null characters and other problematic characters"""
    if not isinstance(s, str):
        return s
    return ''.join(char for char in s if ord(char) >= 32 or char in '\n\r\t')


def sanitize_dict(data):
    """Recursively sanitize all strings in a dictionary"""
    if isinstance(data, dict):
        return {k: sanitize_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_dict(item) for item in data]
    elif isinstance(data, str):
        return sanitize_string(data)
    else:
        return data


# ============================================================================
# ACTIVITY LOG ENDPOINTS
# ============================================================================

class ProjectActivityLogView(APIView):
    """Get activity log for a project"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        """Get activity logs for a project"""
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        # Get query parameters
        limit = request.GET.get('limit', 100)
        try:
            limit = int(limit)
            limit = min(limit, 500)  # Max 500 logs
        except ValueError:
            limit = 100
        
        action_filter = request.GET.get('action', None)
        
        # Query logs
        logs = project.activity_logs_new.all()
        
        if action_filter:
            logs = logs.filter(action=action_filter)
        
        logs = logs[:limit]
        
        serializer = ActivityLogListSerializer(
            logs,
            many=True,
            context={'request': request}
        )
        
        return Response(sanitize_dict({
            'project_id': project.id,
            'project_name': project.name,
            'log_count': logs.count(),
            'activities': serializer.data
        }))


class UserActivityLogView(APIView):
    """Get activity log for current user"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get all activities by current user"""
        # Get query parameters
        limit = request.GET.get('limit', 50)
        try:
            limit = int(limit)
            limit = min(limit, 200)  # Max 200 logs
        except ValueError:
            limit = 50
        
        logs = ActivityLog.objects.filter(user=request.user)[:limit]
        
        serializer = ActivityLogSerializer(
            logs,
            many=True,
            context={'request': request}
        )
        
        return Response(sanitize_dict({
            'user_id': request.user.id,
            'username': request.user.username,
            'log_count': logs.count(),
            'activities': serializer.data
        }))


class ActivityLogDetailView(APIView):
    """Get details of a specific activity log"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, log_id):
        """Get activity log details"""
        log = get_object_or_404(ActivityLog, id=log_id)
        
        # Check if user can view this project
        if not log.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ActivityLogSerializer(log, context={'request': request})
        return Response(sanitize_dict(serializer.data))