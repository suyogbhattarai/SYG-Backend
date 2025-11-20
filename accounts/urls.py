# accounts/urls.py
"""
URL patterns for accounts app
"""

from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RegisterView,
    LoginView,
    LogoutView,
    UserProfileView,
    UpdateProfileView,
    ChangePasswordView,
    RegenerateAPIKeyView,
    DeleteAccountView,
    CheckAuthView,
    SearchUsersView,
    CustomTokenObtainPairView,
)

app_name = 'accounts'

urlpatterns = [
    # Authentication endpoints
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('check/', CheckAuthView.as_view(), name='check-auth'),
    
    # JWT Token endpoints
    path('token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    
    # Profile management
    path('profile/', UserProfileView.as_view(), name='profile'),
    path('profile/update/', UpdateProfileView.as_view(), name='update-profile'),
    path('profile/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('profile/regenerate-api-key/', RegenerateAPIKeyView.as_view(), name='regenerate-api-key'),
    path('profile/delete/', DeleteAccountView.as_view(), name='delete-account'),
    
    # User search
    path('users/search/', SearchUsersView.as_view(), name='search-users'),
]