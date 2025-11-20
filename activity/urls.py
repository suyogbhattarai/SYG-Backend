# activity/urls.py
"""
URL patterns for activity app
"""

from django.urls import path
from .views import (
    ProjectActivityLogView,
    UserActivityLogView,
    ActivityLogDetailView,
)

app_name = 'activity'

urlpatterns = [
    # Activity log endpoints
    path('projects/<int:project_id>/', ProjectActivityLogView.as_view(), name='project-logs'),
    path('user/', UserActivityLogView.as_view(), name='user-logs'),
    path('<int:log_id>/', ActivityLogDetailView.as_view(), name='detail'),
]