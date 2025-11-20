

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from django.shortcuts import get_object_or_404
from django.db.models import Count, Exists, OuterRef, Q
from django.contrib.auth.models import User
from .models import (
    UserProfile, Project, ProjectMember, Version, 
    PendingPush, ActivityLog, SampleBasket
)
from .serializers import (
    UserSerializer, UserProfileSerializer, ProjectSerializer,
    ProjectMemberSerializer, VersionSerializer, PendingPushSerializer,
    ActivityLogSerializer, SampleBasketSerializer, ProjectStatusSerializer
)
from .permissions import IsProjectOwner, CanViewProject, CanEditProject
from .authentication import APIKeyAuthentication
from .tasks import process_pending_push
import json


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
# USER & AUTH ENDPOINTS
# ============================================================================

class UserProfileView(APIView):
    """Get current user's profile and API key"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        profile = request.user.profile
        serializer = UserProfileSerializer(profile, context={'request': request})
        return Response(serializer.data)


class RegenerateAPIKeyView(APIView):
    """Regenerate user's API key"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        profile = request.user.profile
        new_key = profile.regenerate_api_key()
        return Response({
            'api_key': new_key,
            'message': 'API key regenerated successfully'
        })


# ============================================================================
# PROJECT ENDPOINTS
# ============================================================================

class ProjectListCreateView(APIView):
    """
    GET: List all projects user has access to
    POST: Create a new project
    """
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members__user=request.user)
        ).distinct().annotate(
            version_count=Count('versions')
        ).order_by('-updated_at')
        
        serializer = ProjectSerializer(projects, many=True, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def post(self, request):
        serializer = ProjectSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            project = serializer.save(owner=request.user)
            return Response(sanitize_dict(serializer.data), status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProjectDetailView(APIView):
    """Get, update, or delete a project"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        serializer = ProjectSerializer(project, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def put(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can update settings'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ProjectSerializer(
            project,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            
            ActivityLog.log(
                project=project,
                user=request.user,
                action='settings_changed',
                description='Project settings updated'
            )
            
            return Response(sanitize_dict(serializer.data))
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can delete the project'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        project_name = project.name
        project.delete()
        return Response({
            'message': f'Project "{project_name}" deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# TEAM MANAGEMENT ENDPOINTS
# ============================================================================

class ProjectMembersView(APIView):
    """Manage project team members"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        members = project.members.all()
        serializer = ProjectMemberSerializer(members, many=True, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can add members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = ProjectMemberSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            user_id = serializer.validated_data['user_id']
            user = get_object_or_404(User, id=user_id)
            
            if project.members.filter(user=user).exists():
                return Response(
                    {'error': 'User is already a member of this project'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if user == project.owner:
                return Response(
                    {'error': 'Project owner is automatically a member'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            member = serializer.save(project=project, user=user, added_by=request.user)
            return Response(
                ProjectMemberSerializer(member, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ProjectMemberDetailView(APIView):
    """Update or remove a project member"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def put(self, request, project_id, member_id):
        project = get_object_or_404(Project, id=project_id)
        
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can update member roles'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        member = get_object_or_404(ProjectMember, id=member_id, project=project)
        
        serializer = ProjectMemberSerializer(
            member,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            
            ActivityLog.log(
                project=project,
                user=request.user,
                action='member_role_changed',
                description=f"{member.user.username}'s role changed to {member.role}",
                metadata={'member_username': member.user.username, 'new_role': member.role}
            )
            
            return Response(sanitize_dict(serializer.data))
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, project_id, member_id):
        project = get_object_or_404(Project, id=project_id)
        
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can remove members'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        member = get_object_or_404(ProjectMember, id=member_id, project=project)
        member_username = member.user.username
        
        ActivityLog.log(
            project=project,
            user=request.user,
            action='member_removed',
            description=f'{member_username} was removed from the project',
            metadata={'member_username': member_username}
        )
        
        member.delete()
        return Response({
            'message': f'Member {member_username} removed successfully'
        }, status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# VERSION MANAGEMENT ENDPOINTS
# ============================================================================

class VersionUploadView(APIView):
    """Create a new version push request from plugin"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        project_name = sanitize_string(request.data.get('project_name', ''))
        commit_message = sanitize_string(request.data.get('commit_message', 'Version from DAW plugin'))
        file_list = request.data.get('file_list', [])
        
        if not project_name:
            return Response(
                {'error': 'project_name is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not isinstance(file_list, list):
            return Response(
                {'error': 'file_list must be an array'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        file_list = sanitize_dict(file_list)
        
        try:
            project = Project.objects.get(
                Q(owner=request.user) | Q(members__user=request.user),
                name=project_name
            )
        except Project.DoesNotExist:
            project = Project.objects.create(owner=request.user, name=project_name)
        
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
                    if self._matches_pattern(rel_path, pattern):
                        should_ignore = True
                        break
                
                if not should_ignore:
                    filtered_file_list.append(file_entry)
            
            file_list = filtered_file_list
        
        version = Version.objects.create(
            project=project,
            commit_message=commit_message,
            created_by=request.user
        )
        
        initial_status = 'pending'
        if project.require_push_approval and request.user != project.owner:
            initial_status = 'awaiting_approval'
        
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
        
        if initial_status == 'pending':
            try:
                process_pending_push.delay(pending_push.id)
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
    
    @staticmethod
    def _matches_pattern(path, pattern):
        import fnmatch
        return fnmatch.fnmatch(path, pattern)


class ProjectVersionsView(APIView):
    """Get all versions for a project"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        versions = project.versions.all().order_by('-created_at')
        serializer = VersionSerializer(versions, many=True, context={'request': request})
        
        return Response(sanitize_dict({
            'project_id': project.id,
            'project_name': project.name,
            'version_count': versions.count(),
            'versions': serializer.data
        }))


class VersionDetailView(APIView):
    """Get or delete a specific version"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, version_id):
        version = get_object_or_404(Version, id=version_id)
        self.check_object_permissions(request, version)
        
        serializer = VersionSerializer(version, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def delete(self, request, version_id):
        version = get_object_or_404(Version, id=version_id)
        project = version.project
        
        if project.owner != request.user and version.created_by != request.user:
            return Response(
                {'error': 'Only project owner or version creator can delete versions'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        version_num = version.get_version_number()
        
        ActivityLog.log(
            project=project,
            user=request.user,
            action='version_deleted',
            description=f'Version {version_num} deleted',
            metadata={'version_id': version_id, 'version_number': version_num}
        )
        
        version.delete()
        return Response({
            'message': f'Version {version_num} deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)


# ============================================================================
# PUSH MANAGEMENT & APPROVAL ENDPOINTS
# ============================================================================

class PushStatusView(APIView):
    """Get status of a specific push"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, push_id):
        push = get_object_or_404(PendingPush, id=push_id)
        
        if not push.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = PendingPushSerializer(push, context={'request': request})
        return Response(sanitize_dict(serializer.data))


class ApprovePushView(APIView):
    """Approve a pending push (owner only)"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_id):
        push = get_object_or_404(PendingPush, id=push_id)
        project = push.project
        
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can approve pushes'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if push.status != 'awaiting_approval':
            return Response(
                {'error': f'Cannot approve push with status: {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        push.approve(request.user)
        
        ActivityLog.log(
            project=project,
            user=request.user,
            action='push_approved',
            description=f'Approved push from {push.created_by.username}',
            metadata={
                'push_id': push.id,
                'creator': push.created_by.username
            }
        )
        
        try:
            process_pending_push.delay(push.id)
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
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_id):
        push = get_object_or_404(PendingPush, id=push_id)
        project = push.project
        
        if project.owner != request.user:
            return Response(
                {'error': 'Only project owner can reject pushes'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if push.status != 'awaiting_approval':
            return Response(
                {'error': f'Cannot reject push with status: {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        reason = sanitize_string(request.data.get('reason', ''))
        push.reject(request.user, reason)
        
        ActivityLog.log(
            project=project,
            user=request.user,
            action='push_rejected',
            description=f'Rejected push from {push.created_by.username}',
            metadata={
                'push_id': push.id,
                'creator': push.created_by.username,
                'reason': reason
            }
        )
        
        return Response({
            'message': 'Push rejected',
            'push_id': push.id,
            'reason': reason
        })


class CancelPushView(APIView):
    """Cancel an active push"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def post(self, request, push_id):
        push = get_object_or_404(PendingPush, id=push_id)
        
        if push.created_by != request.user and push.project.owner != request.user:
            return Response(
                {'error': 'Only push creator or project owner can cancel'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        if push.status in ['done', 'failed', 'rejected']:
            return Response(
                {'error': f'Cannot cancel push - already {push.status}'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        push.status = 'failed'
        push.message = 'Cancelled by user'
        push.progress = 100
        push.save()
        
        return Response({
            'message': 'Push cancelled successfully',
            'push_id': push.id
        })


# ============================================================================
# STATUS & ACTIVITY ENDPOINTS
# ============================================================================

class AllProjectsStatusView(APIView):
    """Get status of all projects user has access to"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        projects = Project.objects.filter(
            Q(owner=request.user) | Q(members__user=request.user)
        ).distinct().annotate(
            version_count=Count('versions'),
            has_active=Exists(
                PendingPush.objects.filter(
                    project=OuterRef('pk'),
                    status__in=['pending', 'processing', 'zipping', 'comparing', 'awaiting_approval']
                )
            )
        ).prefetch_related('pendingpush_set').order_by('-updated_at')
        
        serializer = ProjectStatusSerializer(projects, many=True, context={'request': request})
        return Response(sanitize_dict(serializer.data))


class ProjectActivityLogView(APIView):
    """Get activity log for a project"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        logs = project.activity_logs.all()[:100]
        serializer = ActivityLogSerializer(logs, many=True, context={'request': request})
        
        return Response(sanitize_dict({
            'project_id': project.id,
            'project_name': project.name,
            'activities': serializer.data
        }))


# ============================================================================
# SAMPLE BASKET ENDPOINTS
# ============================================================================

class SampleBasketView(APIView):
    """Manage project sample basket"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        samples = project.samples.all().order_by('-uploaded_at')
        serializer = SampleBasketSerializer(samples, many=True, context={'request': request})
        
        return Response(sanitize_dict({
            'project_id': project.id,
            'project_name': project.name,
            'sample_count': samples.count(),
            'samples': serializer.data
        }))
    
    def post(self, request, project_id):
        project = get_object_or_404(Project, id=project_id)
        
        if not project.user_can_edit(request.user):
            return Response(
                {'error': 'You do not have permission to upload samples'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SampleBasketSerializer(data=request.data, context={'request': request})
        if serializer.is_valid():
            sample = serializer.save(project=project, uploaded_by=request.user)
            
            ActivityLog.log(
                project=project,
                user=request.user,
                action='sample_uploaded',
                description=f'Uploaded sample: {sample.name}',
                metadata={'sample_id': sample.id, 'sample_name': sample.name}
            )
            
            return Response(
                SampleBasketSerializer(sample, context={'request': request}).data,
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SampleDetailView(APIView):
    """Get, update, or delete a sample"""
    authentication_classes = [APIKeyAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    
    def get(self, request, sample_id):
        sample = get_object_or_404(SampleBasket, id=sample_id)
        self.check_object_permissions(request, sample)
        
        serializer = SampleBasketSerializer(sample, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def put(self, request, sample_id):
        sample = get_object_or_404(SampleBasket, id=sample_id)
        project = sample.project
        
        if not project.user_can_edit(request.user):
            return Response(
                {'error': 'You do not have permission to update samples'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SampleBasketSerializer(
            sample,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            serializer.save()
            return Response(sanitize_dict(serializer.data))
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def delete(self, request, sample_id):
        sample = get_object_or_404(SampleBasket, id=sample_id)
        project = sample.project
        
        if project.owner != request.user and sample.uploaded_by != request.user:
            return Response(
                {'error': 'Only project owner or sample uploader can delete'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        sample_name = sample.name
        
        ActivityLog.log(
            project=project,
            user=request.user,
            action='sample_deleted',
            description=f'Deleted sample: {sample_name}',
            metadata={'sample_name': sample_name}
        )
        
        sample.delete()
        return Response({
            'message': f'Sample "{sample_name}" deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)