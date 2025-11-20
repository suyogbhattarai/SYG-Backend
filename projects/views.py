# projects/views.py
"""
Project and team management views
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

from .models import Project, ProjectMember
from .serializers import (
    ProjectSerializer,
    ProjectListSerializer,
    ProjectCreateSerializer,
    ProjectUpdateSerializer,
    ProjectMemberSerializer,
    ProjectStatusSerializer
)
from .permissions import IsProjectOwner, CanViewProject, CanEditProject


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
# PROJECT ENDPOINTS
# ============================================================================

class ProjectListCreateView(APIView):
    """
    GET: List all projects user has access to
    POST: Create a new project
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """List all projects for current user"""
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
        """Create a new project"""
        serializer = ProjectCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            project = serializer.save(owner=request.user)
            
            # Return full project details
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
    """Get, update, or delete a project"""
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        """Get project details"""
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        serializer = ProjectSerializer(project, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def put(self, request, project_id):
        """Update project settings"""
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        # Only owner can update
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can update settings'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ProjectUpdateSerializer(
            project,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            
            # Log activity (will implement when activity app is created)
            # ActivityLog.log(...)
            
            response_serializer = ProjectSerializer(
                project,
                context={'request': request}
            )
            return Response(sanitize_dict(response_serializer.data))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, project_id):
        """Partial update project settings"""
        return self.put(request, project_id)
    
    @transaction.atomic
    def delete(self, request, project_id):
        """Delete a project and all associated files"""
        project = get_object_or_404(Project, id=project_id)
        
        # Only owner can delete
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can delete the project'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        project_name = project.name
        
  
        
        # Delete the project (this will cascade to related models)
        # The CASCADE setting on ForeignKeys will automatically delete:
        # - ProjectMembers
        # - Versions (which will trigger their delete methods)
        # - PendingPushes
        # - SampleBaskets (which will trigger their delete methods)
        project.delete()
        
        return Response({
            'message': f'Project "{project_name}" deleted successfully'
        }, status=status.HTTP_200_OK)


# ============================================================================
# TEAM MANAGEMENT ENDPOINTS
# ============================================================================

class ProjectMembersView(APIView):
    """Manage project team members"""
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        """Get all project members"""
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        members = project.members_new.all()
        serializer = ProjectMemberSerializer(
            members,
            many=True,
            context={'request': request}
        )
        return Response(sanitize_dict(serializer.data))
    
    def post(self, request, project_id):
        """Add a new member to the project"""
        project = get_object_or_404(Project, id=project_id)
        
        # Only owner can add members
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can add members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ProjectMemberSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            user = get_object_or_404(User, id=user_id)
            
            # Check if user is already a member
            if project.members_new.filter(user=user).exists():
                return Response(
                    {'error': 'User is already a member of this project'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if user is the owner
            if user == project.owner:
                return Response(
                    {'error': 'Project owner is automatically a member'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Create member
            member = ProjectMember.objects.create(
                project=project,
                user=user,
                role=serializer.validated_data['role'],
                added_by=request.user
            )
            
            # Log activity (will implement when activity app is created)
            # ActivityLog.log(...)
            
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
    """Update or remove a project member"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request, project_id, member_id):
        """Update member role"""
        project = get_object_or_404(Project, id=project_id)
        
        # Only owner can update roles
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can update member roles'},
                status=status.HTTP_403_FORBIDDEN
            )
        
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
            
            # Log activity (will implement when activity app is created)
            # ActivityLog.log(...)
            
            return Response(sanitize_dict(serializer.data))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, project_id, member_id):
        """Partial update member role"""
        return self.put(request, project_id, member_id)
    
    def delete(self, request, project_id, member_id):
        """Remove member from project"""
        project = get_object_or_404(Project, id=project_id)
        
        # Only owner can remove members
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can remove members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        member = get_object_or_404(
            ProjectMember,
            id=member_id,
            project=project
        )
        
        member_username = member.user.username
        
        # Log activity (will implement when activity app is created)
        # ActivityLog.log(...)
        
        member.delete()
        
        return Response({
            'message': f'Member {member_username} removed successfully'
        }, status=status.HTTP_200_OK)


# ============================================================================
# STATUS ENDPOINTS
# ============================================================================

class AllProjectsStatusView(APIView):
    """Get status of all projects user has access to"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get lightweight status for all projects"""
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members_new__user=request.user)
        ).distinct().order_by('-updated_at')
        
        serializer = ProjectStatusSerializer(
            projects,
            many=True,
            context={'request': request}
        )
        
        return Response(sanitize_dict(serializer.data))