# projects/views.py
"""
Project views with UID support and secure 404 responses
"""

import os
import shutil
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.contrib.auth.models import User
from django.conf import settings
from django.db import transaction
from django.http import Http404

from .models import Project, ProjectMember
from .serializers import (
    ProjectSerializer,
    ProjectListSerializer,
    ProjectCreateSerializer,
    ProjectUpdateSerializer,
    ProjectMemberSerializer,
    ProjectStatusSerializer
)


def sanitize_string(s):
    """Remove null characters"""
    if not isinstance(s, str):
        return s
    return ''.join(char for char in s if ord(char) >= 32 or char in '\n\r\t')


def sanitize_dict(data):
    """Recursively sanitize strings"""
    if isinstance(data, dict):
        return {k: sanitize_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_dict(item) for item in data]
    elif isinstance(data, str):
        return sanitize_string(data)
    else:
        return data


def get_project_or_404(uid_or_id, user):
    """Get project by UID or return 404"""
    try:
        project = Project.objects.get(uid=uid_or_id)
    except Project.DoesNotExist:
        raise Http404("Project not found")
    
    # Return 404 instead of 403 for security
    if not project.user_can_view(user):
        raise Http404("Project not found")
    
    return project


# ============================================================================
# PROJECT ENDPOINTS
# ============================================================================

class ProjectListCreateView(APIView):
    """List and create projects"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """List all user's projects"""
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members_new__user=request.user)
        ).distinct().order_by('-updated_at')
        
        serializer = ProjectListSerializer(
            projects,
            many=True,
            context={'request': request}
        )
        return Response(sanitize_dict(serializer.data))
    
    def post(self, request):
        """Create new project"""
        serializer = ProjectCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            project = serializer.save(owner=request.user)
            
            response_serializer = ProjectSerializer(
                project,
                context={'request': request}
            )
            
            return Response(
                sanitize_dict(response_serializer.data),
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProjectDetailView(APIView):
    """Get, update, or delete project"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, project_uid):
        """Get project details"""
        project = get_project_or_404(project_uid, request.user)
        
        serializer = ProjectSerializer(project, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def put(self, request, project_uid):
        """Update project"""
        project = get_project_or_404(project_uid, request.user)
        
        # Only owner can update
        if project.owner != request.user:
            raise Http404("Project not found")
        
        serializer = ProjectUpdateSerializer(
            project,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            
            response_serializer = ProjectSerializer(
                project,
                context={'request': request}
            )
            return Response(sanitize_dict(response_serializer.data))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, project_uid):
        """Partial update"""
        return self.put(request, project_uid)
    
    @transaction.atomic
    def delete(self, request, project_uid):
        """Delete project"""
        project = get_project_or_404(project_uid, request.user)
        
        # Only owner can delete
        if project.owner != request.user:
            raise Http404("Project not found")
        
        project_name = project.name
        project.delete()
        
        return Response({
            'message': f'Project "{project_name}" deleted successfully'
        }, status=status.HTTP_200_OK)


# ============================================================================
# TEAM MANAGEMENT
# ============================================================================

class ProjectMembersView(APIView):
    """Manage project members"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, project_uid):
        """Get all members"""
        project = get_project_or_404(project_uid, request.user)
        
        members = project.members_new.all()
        serializer = ProjectMemberSerializer(
            members,
            many=True,
            context={'request': request}
        )
        return Response(sanitize_dict(serializer.data))
    
    def post(self, request, project_uid):
        """Add member"""
        project = get_project_or_404(project_uid, request.user)
        
        # Only owner can add members
        if project.owner != request.user:
            raise Http404("Project not found")
        
        serializer = ProjectMemberSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            user = get_object_or_404(User, id=user_id)
            
            # Check if already member
            if project.members_new.filter(user=user).exists():
                return Response(
                    {'error': 'User is already a member'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if owner
            if user == project.owner:
                return Response(
                    {'error': 'Owner is automatically a member'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create member
            member = ProjectMember.objects.create(
                project=project,
                user=user,
                role=serializer.validated_data['role'],
                added_by=request.user
            )
            
            response_serializer = ProjectMemberSerializer(
                member,
                context={'request': request}
            )
            return Response(
                sanitize_dict(response_serializer.data),
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProjectMemberDetailView(APIView):
    """Update or remove member"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, project_uid, member_id):
        """Update member role"""
        project = get_project_or_404(project_uid, request.user)
        
        # Only owner can update
        if project.owner != request.user:
            raise Http404("Project not found")
        
        member = get_object_or_404(
            ProjectMember,
            id=member_id,
            project=project
        )
        
        serializer = ProjectMemberSerializer(
            member,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            return Response(sanitize_dict(serializer.data))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, project_uid, member_id):
        """Partial update"""
        return self.put(request, project_uid, member_id)
    
    def delete(self, request, project_uid, member_id):
        """Remove member"""
        project = get_project_or_404(project_uid, request.user)
        
        # Only owner can remove
        if project.owner != request.user:
            raise Http404("Project not found")
        
        member = get_object_or_404(
            ProjectMember,
            id=member_id,
            project=project
        )
        
        member_username = member.user.username
        member.delete()
        
        return Response({
            'message': f'Member {member_username} removed successfully'
        }, status=status.HTTP_200_OK)


# ============================================================================
# STATUS ENDPOINTS
# ============================================================================

class AllProjectsStatusView(APIView):
    """Get status of all projects"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get lightweight status"""
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members_new__user=request.user)
        ).distinct().order_by('-updated_at')
        
        serializer = ProjectStatusSerializer(
            projects,
            many=True,
            context={'request': request}
        )
        
        return Response(sanitize_dict(serializer.data))
    
class SimpleTestView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        return Response({'status': 'POST works!'})