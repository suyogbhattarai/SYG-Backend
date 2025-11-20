# samples/views.py
"""
Sample basket management views
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.shortcuts import get_object_or_404

from projects.models import Project
from projects.permissions import CanViewProject, CanEditProject
from .models import SampleBasket
from .serializers import (
    SampleBasketSerializer,
    SampleBasketCreateSerializer,
    SampleBasketUpdateSerializer,
    SampleBasketListSerializer
)


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
# SAMPLE BASKET ENDPOINTS
# ============================================================================

class SampleBasketView(APIView):
    """Manage project sample basket"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, CanViewProject]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    
    def get(self, request, project_id):
        """Get all samples for a project"""
        project = get_object_or_404(Project, id=project_id)
        self.check_object_permissions(request, project)
        
        samples = project.samples_new.all().order_by('-uploaded_at')
        serializer = SampleBasketListSerializer(
            samples,
            many=True,
            context={'request': request}
        )
        
        return Response(sanitize_dict({
            'project_id': project.id,
            'project_name': project.name,
            'sample_count': samples.count(),
            'samples': serializer.data
        }))
    
    def post(self, request, project_id):
        """Upload a new sample to the project"""
        project = get_object_or_404(Project, id=project_id)
        
        # Check edit permission
        if not project.user_can_edit(request.user):
            return Response(
                {'error': 'You do not have permission to upload samples'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SampleBasketCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
            sample = serializer.save(
                project=project,
                uploaded_by=request.user
            )
            
            # Log activity (will implement when activity app is created)
            # ActivityLog.log(...)
            
            response_serializer = SampleBasketSerializer(
                sample,
                context={'request': request}
            )
            
            return Response(
                sanitize_dict(response_serializer.data),
                status=status.HTTP_201_CREATED
            )
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class SampleDetailView(APIView):
    """Get, update, or delete a sample"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]
    
    def get(self, request, sample_id):
        """Get sample details"""
        sample = get_object_or_404(SampleBasket, id=sample_id)
        
        # Check view permission
        if not sample.project.user_can_view(request.user):
            return Response(
                {'error': 'Access denied'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SampleBasketSerializer(sample, context={'request': request})
        return Response(sanitize_dict(serializer.data))
    
    def put(self, request, sample_id):
        """Update sample metadata"""
        sample = get_object_or_404(SampleBasket, id=sample_id)
        project = sample.project
        
        # Check edit permission
        if not project.user_can_edit(request.user):
            return Response(
                {'error': 'You do not have permission to update samples'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        serializer = SampleBasketUpdateSerializer(
            sample,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        
        if serializer.is_valid():
            serializer.save()
            
            response_serializer = SampleBasketSerializer(
                sample,
                context={'request': request}
            )
            return Response(sanitize_dict(response_serializer.data))
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
    def patch(self, request, sample_id):
        """Partial update sample metadata"""
        return self.put(request, sample_id)
    
    def delete(self, request, sample_id):
        """Delete a sample"""
        sample = get_object_or_404(SampleBasket, id=sample_id)
        project = sample.project
        
        # Only owner or uploader can delete
        if project.owner != request.user and sample.uploaded_by != request.user:
            return Response(
                {'error': 'Only project owner or sample uploader can delete'},
                status=status.HTTP_403_FORBIDDEN
            )
        
        sample_name = sample.name
        
        # Log activity (will implement when activity app is created)
        # ActivityLog.log(...)
        
        sample.delete()
        
        return Response({
            'message': f'Sample "{sample_name}" deleted successfully'
        }, status=status.HTTP_204_NO_CONTENT)