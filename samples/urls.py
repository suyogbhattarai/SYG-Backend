from django.urls import path
from .views import SampleBasketView, SampleDetailView

app_name = 'samples'

urlpatterns = [
    # Use project UID instead of ID
    path('projects/<str:project_uid>/', SampleBasketView.as_view(), name='project-samples'),
    # Use sample UID instead of ID
    path('<str:sample_uid>/', SampleDetailView.as_view(), name='detail'),
]
