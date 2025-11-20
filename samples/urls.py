# samples/urls.py
"""
URL patterns for samples app
"""

from django.urls import path
from .views import (
    SampleBasketView,
    SampleDetailView,
)

app_name = 'samples'

urlpatterns = [
    # Sample basket endpoints
    path('projects/<int:project_id>/', SampleBasketView.as_view(), name='project-samples'),
    path('<int:sample_id>/', SampleDetailView.as_view(), name='detail'),
]