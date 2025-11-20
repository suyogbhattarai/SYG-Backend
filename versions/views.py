"""
versions/views.py
Version control and push management views with CAS support
Optimized to handle cancellation and version status properly
"""

import os
import tempfile
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import FileResponse, HttpResponse, Http404

from projects.models import Project
from projects.permissions import CanViewProject, CanEditProject
from .models import Version, PendingPush, DownloadRequest
from .serializers import (
    VersionSerializer,
    VersionListSerializer,
    PendingPushSerializer,
    VersionUploadSerializer,
    DownloadRequestSerializer
)
from .tasks import process_pending_push_new
from .download_tasks import create_download_zip
from .restore_utils import get_version_file_list
import fnmatch


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
# VERSION ENDPOINTS
# ============================================================================

class ProjectVersionsView(APIView):
    """Get all versions for a project (only completed ones by default)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        """List all versions for a project"""
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        # Query parameter to include processing versions
        include_processing = request.query_params.get('include_processing', 'false').lower() == 'true'
        
        if include_processing:
            versions = project.versions_new.all().order_by('-created_at')
        else:
            # Default: only show completed versions
            versions = project.versions_new.filter(status__in=['completed', 'processing']).order_by('-created_at')
        
        serializer = VersionListSerializer(
            versions,
            many=True,
            context={'request': request}
        )
        
        return Response(sanitize_dict({
            'project_id': project.id,
            'project_name': project.name,
            'version_count': versions.count(),
            'completed_count': project.versions_new.filter(status='completed').count(),
            'processing_count': project.versions_new.filter(status='processing').count(),
            'versions': serializer.data
        }))


class VersionDetailView(APIView):
    """Get or delete a specific version"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, version_id):
        """Get version details"""
        version = get_object_or_404(Version, id=version_id)
        
        # Check permissions
        if not version.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = VersionSerializer(version, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def delete(self, request, version_id):
        """Delete a version"""
        version = get_object_or_404(Version, id=version_id)
        project = version.project
        
        # Only owner or creator can delete
        if project.owner != request.user and version.created_by != request.user:
            return Response(
                {'error': 'Only project owner or version creator can delete versions'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Get version number before deletion (only for completed versions)
        version_num = version.get_version_number() if version.status == 'completed' else None
        version_status = version.status
        
        version.delete()
        
        message = f'Version deleted successfully'
        if version_num:
            message = f'Version {version_num} deleted successfully'
        elif version_status != 'completed':
            message = f'Version (status: {version_status}) deleted successfully'
        
        return Response({
            'message': message
        }, status=status.HTTP_204_NO_CONTENT)


class VersionUploadView(APIView):
    """Create a new version push request from plugin"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Handle version upload from DAW plugin"""
        serializer = VersionUploadSerializer(data=request.data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        
        project_name = sanitize_string(serializer.validated_data['project_name'])
        commit_message = sanitize_string(serializer.validated_data['commit_message'])
        file_list = sanitize_dict(serializer.validated_data['file_list'])
        
        # Get or create project
        try:
            project = Project.objects.get(
                Q(owner=request.user) | Q(members_new__user=request.user),
                name=project_name
            )
        except Project.DoesNotExist:
            project = Project.objects.create(
                owner=request.user,
                name=project_name
            )
        
        # Check edit permission
        if not project.user_can_edit(request.user):
            return Response(
                {'error': 'You do not have permission to push to this project'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Filter files based on ignore patterns
        if project.ignore_patterns:
            filtered_file_list = []
            for file_entry in file_list:
                rel_path = file_entry.get('relative_path', '')
                should_ignore = False
                
                for pattern in project.ignore_patterns:
                    if fnmatch.fnmatch(rel_path, pattern):
                        should_ignore = True
                        break
                
                if not should_ignore:
                    filtered_file_list.append(file_entry)
            
            file_list = filtered_file_list
        
        # Create version placeholder with 'pending' status
        version = Version.objects.create(
            project=project,
            commit_message=commit_message,
            created_by=request.user,
            status='pending'  # Will be updated to 'processing' then 'completed'
        )
        
        # Determine initial status
        initial_status = 'pending'
        if project.require_push_approval and request.user != project.owner:
            initial_status = 'awaiting_approval'
        
        # Create pending push
        pending_push = PendingPush.objects.create(
            project=project,
            created_by=request.user,
            commit_message=commit_message,
            file_list=file_list,
            version=version,
            status=initial_status,
            progress=0,
            message='Push request received' if initial_status == 'pending' else 'Awaiting approval from project owner'
        )
        
        # Start processing if no approval needed
        if initial_status == 'pending':
            try:
                process_pending_push_new.delay(pending_push.id)
            except Exception as e:
                pending_push.mark_failed(str(e))
                return Response({
                    'error': 'Failed to queue processing task',
                    'details': str(e)
                }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response(sanitize_dict({
            'push_id': pending_push.id,
            'project_id': project.id,
            'project_name': project.name,
            'version_id': version.id,
            'message': 'Push initiated' if initial_status == 'pending' else 'Push awaiting approval',
            'status': initial_status,
            'requires_approval': initial_status == 'awaiting_approval'
        }), status=status.HTTP_201_CREATED)


# ============================================================================
# VERSION RESTORE/DOWNLOAD ENDPOINTS
# ============================================================================

class RequestVersionDownloadView(APIView):
    """Request creation of a download ZIP (initiates async task)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, version_id):
        """Request download ZIP creation"""
        version = get_object_or_404(Version, id=version_id)
        
        # Check permissions
        if not version.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if version is ready
        if not version.is_ready():
            return Response({
                'error': 'Version is not ready for download',
                'status': version.status,
                'message': 'This version is still being processed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if there's already a recent download request
        from django.utils import timezone
        from datetime import timedelta
        
        recent_request = DownloadRequest.objects.filter(
            version=version,
            requested_by=request.user,
            status__in=['pending', 'processing', 'completed'],
            created_at__gte=timezone.now() - timedelta(minutes=30)
        ).first()
        
        if recent_request:
            if recent_request.status == 'completed' and not recent_request.is_expired():
                # Return existing completed download
                serializer = DownloadRequestSerializer(recent_request, context={'request': request})
                return Response({
                    'message': 'Using existing download',
                    'download': sanitize_dict(serializer.data)
                })
            elif recent_request.status in ['pending', 'processing']:
                # Return existing in-progress request
                serializer = DownloadRequestSerializer(recent_request, context={'request': request})
                return Response({
                    'message': 'Download already in progress',
                    'download': sanitize_dict(serializer.data)
                })
        
        # Create new download request
        download_request = DownloadRequest.objects.create(
            version=version,
            requested_by=request.user,
            status='pending',
            progress=0,
            message='Download request queued'
        )
        
        # Queue the ZIP creation task
        try:
            create_download_zip.delay(download_request.id)
        except Exception as e:
            download_request.mark_failed(str(e))
            return Response({
                'error': 'Failed to queue download task',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        serializer = DownloadRequestSerializer(download_request, context={'request': request})
        
        return Response({
            'message': 'Download request created',
            'download': sanitize_dict(serializer.data)
        }, status=status.HTTP_201_CREATED)


class DownloadRequestStatusView(APIView):
    """Check status of a download request (for polling)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, download_id):
        """Get download request status"""
        download_request = get_object_or_404(DownloadRequest, id=download_id)
        
        # Check permissions
        if not download_request.version.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = DownloadRequestSerializer(download_request, context={'request': request})
        return Response(sanitize_dict(serializer.data))


class VersionDownloadView(APIView):
    """Download the ZIP file directly"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, download_id):
        """Download the ZIP file"""
        download_request = get_object_or_404(DownloadRequest, id=download_id)
        
        # Check permissions
        if not download_request.version.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if download is ready
        if download_request.status != 'completed':
            return Response({
                'error': 'Download not ready',
                'status': download_request.status,
                'progress': download_request.progress,
                'message': download_request.message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check if expired
        if download_request.is_expired():
            return Response({
                'error': 'Download has expired',
                'message': 'Please request a new download'
            }, status=status.HTTP_410_GONE)
        
        # Serve the file
        if not download_request.zip_file:
            return Response({
                'error': 'Download file not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            version = download_request.version
            filename = f"{version.project.name}_v{version.get_version_number()}.zip"
            
            response = FileResponse(
                open(download_request.zip_file.path, 'rb'),
                as_attachment=True,
                filename=filename
            )
            
            return response
        
        except Exception as e:
            return Response({
                'error': 'Failed to serve download',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class VersionFileListView(APIView):
    """Get list of files in a version"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, version_id):
        """Get file list from version"""
        version = get_object_or_404(Version, id=version_id)
        
        # Check permissions
        if not version.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check if version is ready
        if not version.is_ready():
            return Response({
                'error': 'Version is not ready',
                'status': version.status,
                'message': 'This version is still being processed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            files = get_version_file_list(version)
            
            return Response({
                'version_id': version.id,
                'version_number': version.get_version_number(),
                'storage_type': version.get_storage_type(),
                'file_count': len(files),
                'files': files
            })
        
        except Exception as e:
            return Response({
                'error': 'Failed to get file list',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PUSH MANAGEMENT ENDPOINTS
# ============================================================================

class PushStatusView(APIView):
    """Get status of a specific push"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, push_id):
        """Get push status"""
        push = get_object_or_404(PendingPush, id=push_id)
        
        # Check permissions
        if not push.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = PendingPushSerializer(push, context={'request': request})
        return Response(sanitize_dict(serializer.data))


class ApprovePushView(APIView):
    """Approve a pending push (owner only)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_id):
        """Approve push and start processing"""
        push = get_object_or_404(PendingPush, id=push_id)
        project = push.project
        
        # Only owner can approve
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can approve pushes'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check status
        if push.status != 'awaiting_approval':
            return Response(
                {'error': f'Cannot approve push with status: {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Approve
        push.approve(request.user)
        
        # Start processing
        try:
            process_pending_push_new.delay(push.id)
        except Exception as e:
            push.mark_failed(str(e))
            return Response({
                'error': 'Failed to queue processing task',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        
        return Response({
            'message': 'Push approved and processing started',
            'push_id': push.id
        })


class RejectPushView(APIView):
    """Reject a pending push (owner only)"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_id):
        """Reject push and cleanup associated version"""
        push = get_object_or_404(PendingPush, id=push_id)
        project = push.project
        
        # Only owner can reject
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can reject pushes'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check status
        if push.status != 'awaiting_approval':
            return Response(
                {'error': f'Cannot reject push with status: {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Reject (will automatically delete associated version)
        reason = sanitize_string(request.data.get('reason', ''))
        push.reject(request.user, reason)
        
        return Response({
            'message': 'Push rejected and version removed',
            'push_id': push.id,
            'reason': reason
        })


class CancelPushView(APIView):
    """Cancel an active push"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_id):
        """Cancel push and cleanup associated version"""
        push = get_object_or_404(PendingPush, id=push_id)
        
        # Only creator or owner can cancel
        if push.created_by != request.user and push.project.owner != request.user:
            return Response(
                {'error': 'Only push creator or project owner can cancel'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Check status
        if push.status in ['done', 'failed', 'rejected', 'cancelled']:
            return Response(
                {'error': f'Cannot cancel push - already {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        # Cancel (will automatically delete associated version)
        push.cancel()
        
        return Response({
            'message': 'Push cancelled successfully and version removed',
            'push_id': push.id
        })