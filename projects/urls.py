# ============================================================================
# projects/urls.py
# ============================================================================

"""
projects/urls.py
UPDATED: Using UIDs instead of IDs
"""

from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMembersView,
    ProjectMemberDetailView,
    AllProjectsStatusView,
    SimpleTestView
)

app_name = 'projects'

urlpatterns = [
    # Project CRUD (using UIDs)
    path('', ProjectListCreateView.as_view(), name='list-create'),
    path('<str:project_uid>/', ProjectDetailView.as_view(), name='detail'),
    
    # Team Management (using UIDs)
    path('<str:project_uid>/members/', ProjectMembersView.as_view(), name='members'),
    path('<str:project_uid>/members/<int:member_id>/', ProjectMemberDetailView.as_view(), name='member-detail'),
    
    # Status
    path('status/', AllProjectsStatusView.as_view(), name='all-status'),

     path('simple-test/', SimpleTestView.as_view(), name='simple-test'),
]