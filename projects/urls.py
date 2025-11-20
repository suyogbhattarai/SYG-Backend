# projects/urls.py
"""
URL patterns for projects app
"""

from django.urls import path
from .views import (
    ProjectListCreateView,
    ProjectDetailView,
    ProjectMembersView,
    ProjectMemberDetailView,
    AllProjectsStatusView,
)

app_name = 'projects'

urlpatterns = [
    # Project CRUD
    path('', ProjectListCreateView.as_view(), name='list-create'),
    path('<int:project_id>/', ProjectDetailView.as_view(), name='detail'),
    
    # Team Management
    path('<int:project_id>/members/', ProjectMembersView.as_view(), name='members'),
    path('<int:project_id>/members/<int:member_id>/', ProjectMemberDetailView.as_view(), name='member-detail'),
    
    # Status
    path('status/', AllProjectsStatusView.as_view(), name='all-status'),
]