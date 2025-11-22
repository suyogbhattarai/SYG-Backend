"""
versions/urls.py
FIXED: Proper URL ordering to prevent pattern conflicts
Specific patterns MUST come before generic catch-all patterns
"""

from django.urls import path
from .views import (
    ProjectVersionsView,
    VersionDetailView,
    VersionUploadView,
    RequestVersionDownloadView,
    DownloadRequestStatusView,
    VersionDownloadView,
    VersionFileListView,
    PushStatusView,
    ApprovePushView,
    RejectPushView,
    CancelPushView,
    SimpleTestView
)

app_name = 'versions'

urlpatterns = [
    # ========================================================================
    # IMPORTANT: Specific patterns MUST come before generic catch-all patterns
    # Django matches URLs from top to bottom and stops at first match
    # ========================================================================
    
    # ========================================================================
    # TEST ENDPOINT (must be first - before any catch-all patterns)
    # ========================================================================
    path('simple-test/', SimpleTestView.as_view(), name='simple-test'),
    
    # ========================================================================
    # VERSION ENDPOINTS - Specific patterns first
    # ========================================================================
    
    # Upload/create new version (POST)
    path('upload/', VersionUploadView.as_view(), name='upload'),
    
    # List versions for a project (GET)
    path('projects/<str:project_uid>/versions/', ProjectVersionsView.as_view(), name='project-versions'),
    
    # ========================================================================
    # DOWNLOAD ENDPOINTS - Specific patterns
    # ========================================================================
    
    # Check download status (GET)
    path('downloads/<str:download_uid>/status/', DownloadRequestStatusView.as_view(), name='download-status'),
    
    # Download ZIP file (GET)
    path('downloads/<str:download_uid>/file/', VersionDownloadView.as_view(), name='download-file'),
    
    # ========================================================================
    # PUSH MANAGEMENT ENDPOINTS - Specific patterns
    # ========================================================================
    
    # Get push status (GET)
    path('pushes/<str:push_uid>/', PushStatusView.as_view(), name='push-status'),
    
    # Approve push (POST)
    path('pushes/<str:push_uid>/approve/', ApprovePushView.as_view(), name='push-approve'),
    
    # Reject push (POST)
    path('pushes/<str:push_uid>/reject/', RejectPushView.as_view(), name='push-reject'),
    
    # Cancel push (POST)
    path('pushes/<str:push_uid>/cancel/', CancelPushView.as_view(), name='push-cancel'),
    
    # ========================================================================
    # VERSION ENDPOINTS - Generic patterns (MUST BE LAST)
    # ========================================================================
    
    # Get file list for a version (GET) - more specific than detail
    path('<str:version_uid>/files/', VersionFileListView.as_view(), name='file-list'),
    
    # Request download ZIP creation (POST) - more specific than detail
    path('<str:version_uid>/request-download/', RequestVersionDownloadView.as_view(), name='request-download'),
    
    # Version detail (GET, DELETE) - MUST BE LAST - catches any remaining UIDs
    # This is a catch-all pattern and will match ANY string
    path('<str:version_uid>/', VersionDetailView.as_view(), name='detail'),
]