"""
versions/views.py
FIXED: UID support, secure 404 responses, and project ID usage
"""

import os
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.http import FileResponse, Http404

from projects.models import Project
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
    """Get project by UID or return 404 (not permission denied)"""
    try:
        project = Project.objects.get(uid=uid_or_id)
    except Project.DoesNotExist:
        raise Http404("Project not found")
    
    # Check permissions - return 404 instead of 403 for security
    if not project.user_can_view(user):
        raise Http404("Project not found")
    
    return project


def get_version_or_404(uid_or_id, user):
    """Get version by UID or return 404"""
    try:
        version = Version.objects.get(uid=uid_or_id)
    except Version.DoesNotExist:
        raise Http404("Version not found")
    
    if not version.project.user_can_view(user):
        raise Http404("Version not found")
    
    return version


def get_download_or_404(uid_or_id, user):
    """Get download request by UID or return 404"""
    try:
        download = DownloadRequest.objects.get(uid=uid_or_id)
    except DownloadRequest.DoesNotExist:
        raise Http404("Download not found")
    
    if not download.version.project.user_can_view(user):
        raise Http404("Download not found")
    
    return download


def get_push_or_404(uid_or_id, user):
    """Get push by UID or return 404"""
    try:
        push = PendingPush.objects.get(uid=uid_or_id)
    except PendingPush.DoesNotExist:
        raise Http404("Push not found")
    
    if not push.project.user_can_view(user):
        raise Http404("Push not found")
    
    return push


# ============================================================================
# VERSION ENDPOINTS
# ============================================================================

class ProjectVersionsView(APIView):
    """Get all versions for a project"""
 
    permission_classes = [IsAuthenticated]
    
    def get(self, request, project_uid):
        """List all versions"""
        project = get_project_or_404(project_uid, request.user)
        
        include_processing = request.query_params.get('include_processing', 'false').lower() == 'true'
        
        if include_processing:
            versions = project.versions_new.all().order_by('-created_at')
        else:
            versions = project.versions_new.filter(
                status__in=['completed', 'processing']
            ).order_by('-created_at')
        
        serializer = VersionListSerializer(
            versions,
            many=True,
            context={'request': request}
        )
        
        return Response(sanitize_dict({
            'project_uid': project.uid,
            'project_name': project.name,
            'project_id': project.id,
            'version_count': versions.count(),
            'completed_count': project.versions_new.filter(status='completed').count(),
            'processing_count': project.versions_new.filter(status='processing').count(),
            'versions': serializer.data
        }))


class VersionDetailView(APIView):
    """Get or delete a specific version"""

    permission_classes = [IsAuthenticated]
    
    def get(self, request, version_uid):
        """Get version details"""
        version = get_version_or_404(version_uid, request.user)
        
        serializer = VersionSerializer(version, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def delete(self, request, version_uid):
        """Delete a version"""
        version = get_version_or_404(version_uid, request.user)
        project = version.project
        
        # Only owner or creator can delete
        if project.owner != request.user and version.created_by != request.user:
            raise Http404("Version not found")
        
        version_num = version.version_number if version.status == 'completed' else None
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
    """Create new version push"""

    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Handle version upload"""
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
        
        if not project.user_can_edit(request.user):
            return Response(
                {'error': 'You do not have permission to push to this project'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        # Filter by ignore patterns
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
        
        # Create version placeholder
        version = Version.objects.create(
            project=project,
            commit_message=commit_message,
            created_by=request.user,
            status='pending'
        )
        
        # Determine status
        initial_status = 'pending'
        if project.require_push_approval and request.user != project.owner:
            initial_status = 'awaiting_approval'
        
        # Create push
        pending_push = PendingPush.objects.create(
            project=project,
            created_by=request.user,
            commit_message=commit_message,
            file_list=file_list,
            version=version,
            status=initial_status,
            progress=0,
            message='Push request received' if initial_status == 'pending' else 'Awaiting approval'
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
            'push_uid': pending_push.uid,
            'project_uid': project.uid,
            'project_id': project.id,
            'project_name': project.name,
            'version_uid': version.uid,
            'message': 'Push initiated' if initial_status == 'pending' else 'Push awaiting approval',
            'status': initial_status,
            'requires_approval': initial_status == 'awaiting_approval'
        }), status=status.HTTP_201_CREATED)


# ============================================================================
# DOWNLOAD ENDPOINTS
# ============================================================================

class RequestVersionDownloadView(APIView):
    """Request download ZIP creation"""
 
    permission_classes = [IsAuthenticated]

    def post(self, request, version_uid):
        """Request download"""
        version = get_version_or_404(version_uid, request.user)
        
        if not version.is_ready():
            return Response({
                'error': 'Version is not ready for download',
                'status': version.status,
                'message': 'This version is still being processed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        # Check for recent download
        from django.utils import timezone
        from datetime import timedelta
        
        recent_request = DownloadRequest.objects.filter(
            version=version,
            requested_by=request.user,
            status__in=['pending', 'processing', 'completed'],
            created_at__gte=timezone.now() - timedelta(hours=DownloadRequest.EXPIRATION_HOURS)
        ).first()
        
        if recent_request:
            if recent_request.status == 'completed' and not recent_request.is_expired():
                serializer = DownloadRequestSerializer(recent_request, context={'request': request})
                return Response({
                    'message': 'Using existing download',
                    'download': sanitize_dict(serializer.data)
                })
            elif recent_request.status in ['pending', 'processing']:
                serializer = DownloadRequestSerializer(recent_request, context={'request': request})
                return Response({
                    'message': 'Download already in progress',
                    'download': sanitize_dict(serializer.data)
                })
        
        # Create new request
        download_request = DownloadRequest.objects.create(
            version=version,
            requested_by=request.user,
            status='pending',
            progress=0,
            message='Download request queued'
        )
        
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
    """Check download status"""

    permission_classes = [IsAuthenticated]
    
    def get(self, request, download_uid):
        """Get download status"""
        download_request = get_download_or_404(download_uid, request.user)
        
        # Check expiration
        if download_request.status == 'completed' and download_request.is_expired():
            download_request.status = 'expired'
            download_request.message = 'Download link has expired. Please request a new download.'
            download_request.save(update_fields=['status', 'message'])
        
        serializer = DownloadRequestSerializer(download_request, context={'request': request})
        return Response(sanitize_dict(serializer.data))


class VersionDownloadView(APIView):
    """Download ZIP file"""

    permission_classes = [IsAuthenticated]
    
    def get(self, request, download_uid):
        """Download file"""
        download_request = get_download_or_404(download_uid, request.user)
        
        if download_request.status != 'completed':
            return Response({
                'error': 'Download not ready',
                'status': download_request.status,
                'progress': download_request.progress,
                'message': download_request.message
            }, status=status.HTTP_400_BAD_REQUEST)
        
        if download_request.is_expired():
            download_request.status = 'expired'
            download_request.message = 'Download link has expired'
            download_request.save(update_fields=['status', 'message'])
            
            return Response({
                'error': 'Download has expired',
                'message': f'Download expired after {download_request.EXPIRATION_HOURS} hours',
                'expiration_hours': download_request.EXPIRATION_HOURS
            }, status=status.HTTP_410_GONE)
        
        if not download_request.zip_file:
            return Response({
                'error': 'Download file not found'
            }, status=status.HTTP_404_NOT_FOUND)
        
        try:
            version = download_request.version
            version_number = version.version_number or 'unknown'
            filename = f"{version.project.name}_v{version_number}.zip"
            
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
    """Get file list from version"""

    permission_classes = [IsAuthenticated]
    
    def get(self, request, version_uid):
        """Get file list"""
        version = get_version_or_404(version_uid, request.user)
        
        if not version.is_ready():
            return Response({
                'error': 'Version is not ready',
                'status': version.status,
                'message': 'This version is still being processed'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            files = get_version_file_list(version)
            
            return Response({
                'version_uid': version.uid,
                'version_number': version.version_number,
                'storage_type': version.get_storage_type(),
                'file_count': len(files),
                'files': files,
                'change_summary': version.get_change_summary()
            })
        
        except Exception as e:
            return Response({
                'error': 'Failed to get file list',
                'details': str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ============================================================================
# PUSH MANAGEMENT
# ============================================================================

class PushStatusView(APIView):
    """Get push status"""

    permission_classes = [IsAuthenticated]
    
    def get(self, request, push_uid):
        """Get status"""
        push = get_push_or_404(push_uid, request.user)
        
        serializer = PendingPushSerializer(push, context={'request': request})
        return Response(sanitize_dict(serializer.data))


class ApprovePushView(APIView):
    """Approve push"""
  
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_uid):
        """Approve"""
        push = get_push_or_404(push_uid, request.user)
        
        if push.project.owner != request.user:
            raise Http404("Push not found")
        
        if push.status != 'awaiting_approval':
            return Response(
                {'error': f'Cannot approve push with status: {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        push.approve(request.user)
        
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
            'push_uid': push.uid
        })


class RejectPushView(APIView):
    """Reject push"""
   
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_uid):
        """Reject"""
        push = get_push_or_404(push_uid, request.user)
        
        if push.project.owner != request.user:
            raise Http404("Push not found")
        
        if push.status != 'awaiting_approval':
            return Response(
                {'error': f'Cannot reject push with status: {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = sanitize_string(request.data.get('reason', ''))
        push.reject(request.user, reason)
        
        return Response({
            'message': 'Push rejected and version removed',
            'push_uid': push.uid,
            'reason': reason
        })


class CancelPushView(APIView):
    """Cancel push"""

    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_uid):
        """Cancel"""
        push = get_push_or_404(push_uid, request.user)
        
        if push.created_by != request.user and push.project.owner != request.user:
            raise Http404("Push not found")
        
        if push.status in ['done', 'failed', 'rejected', 'cancelled']:
            return Response(
                {'error': f'Cannot cancel push - already {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        push.cancel()
        
        return Response({
            'message': 'Push cancelled successfully',
            'push_uid': push.uid
        })
    

class SimpleTestView(APIView):
    authentication_classes = []
    permission_classes = []
    
    def post(self, request):
        return Response({'status': 'POST works!'})