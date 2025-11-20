"""
versions/urls.py
URL patterns for versions app with CAS support and download management
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
)

app_name = 'versions'

urlpatterns = [
    # Version endpoints
    path('projects/<int:project_id>/versions/', ProjectVersionsView.as_view(), name='project-versions'),
    path('<int:version_id>/', VersionDetailView.as_view(), name='detail'),
    path('upload/', VersionUploadView.as_view(), name='upload'),
    
    # Version file list
    path('<int:version_id>/files/', VersionFileListView.as_view(), name='file-list'),
    
    # Download management (new workflow)
    path('<int:version_id>/request-download/', RequestVersionDownloadView.as_view(), name='request-download'),
    path('download/<int:download_id>/status/', DownloadRequestStatusView.as_view(), name='download-status'),
    path('download/<int:download_id>/', VersionDownloadView.as_view(), name='download-file'),
    
    # Push management
    path('push/<int:push_id>/status/', PushStatusView.as_view(), name='push-status'),
    path('push/<int:push_id>/approve/', ApprovePushView.as_view(), name='push-approve'),
    path('push/<int:push_id>/reject/', RejectPushView.as_view(), name='push-reject'),
    path('push/<int:push_id>/cancel/', CancelPushView.as_view(), name='push-cancel'),
]
