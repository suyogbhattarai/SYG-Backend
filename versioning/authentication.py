# versioning/authentication.py - JWT + API Key Support

from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.models import User
from .models import UserProfile


class JWTAndAPIKeyAuthentication(JWTAuthentication):
    """
    Combined JWT and API Key authentication
    Tries JWT first (from Authorization header), then falls back to API key (from X-API-Key header)
    
    This allows:
    1. Modern JWT authentication for web dashboard
    2. Legacy API key support for existing plugin code
    3. Gradual migration from API key to JWT
    """
    
    def authenticate(self, request):
        # First try JWT authentication
        jwt_auth = super().authenticate(request)
        if jwt_auth is not None:
            return jwt_auth
        
        # If JWT fails, try API key authentication
        api_key = request.META.get('HTTP_X_API_KEY')
        
        if not api_key:
            return None  # No authentication provided
        
        try:
            profile = UserProfile.objects.select_related('user').get(api_key=api_key)
            return (profile.user, None)
        except UserProfile.DoesNotExist:
            raise AuthenticationFailed('Invalid API key')


class APIKeyAuthentication(BaseAuthentication):
    """
    Legacy API key authentication (for backward compatibility)
    Use JWTAndAPIKeyAuthentication instead for new code
    """
    def authenticate(self, request):
        api_key = request.META.get('HTTP_X_API_KEY')
        
        if not api_key:
            return None
        
        try:
            profile = UserProfile.objects.select_related('user').get(api_key=api_key)
            return (profile.user, None)
        except UserProfile.DoesNotExist:
            raise AuthenticationFailed('Invalid API key')