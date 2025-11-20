"""
Authentication and user profile views
"""

from rest_framework.views import APIView
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import IntegrityError
from django.db.models import Q

from .models import UserProfile
from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    UserRegistrationSerializer,
    ChangePasswordSerializer,
    UpdateProfileSerializer
)
from .utils.responses import success_response, error_response


def get_tokens_for_user(user):
    """Generate JWT tokens for user"""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


def get_or_create_profile(user):
    """Get or create the NEW UserProfile for a user"""
    profile, _ = UserProfile.objects.get_or_create(
        user=user,
        defaults={'api_key': UserProfile.generate_api_key()}
    )
    return profile


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Custom token serializer with additional user info"""
    
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['username'] = user.username
        token['email'] = user.email
        return token
    
    def validate(self, attrs):
        data = super().validate(attrs)
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
        }
        profile = get_or_create_profile(self.user)
        data['api_key'] = profile.api_key
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom token view"""
    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(APIView):
    """User registration endpoint"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Invalid input data", serializer.errors)

        try:
            user = serializer.save()
            user.refresh_from_db()

            profile = get_or_create_profile(user)
            tokens = get_tokens_for_user(user)

            data = {
                'user': UserSerializer(user).data,
                'tokens': tokens,
                'api_key': profile.api_key,
            }
            return success_response("Registration successful", data, status.HTTP_201_CREATED)

        except IntegrityError as e:
            return error_response("Registration failed due to duplicate entry", {"detail": str(e)})
        except Exception as e:
            return error_response("Registration failed due to server error", {"detail": str(e)}, status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(APIView):
    """User login endpoint"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        username = request.data.get('username', '').strip()
        password = request.data.get('password', '')

        if not username or not password:
            return error_response("Username and password are required")

        user = authenticate(request, username=username, password=password)
        if not user:
            return error_response("Invalid username or password", code=status.HTTP_401_UNAUTHORIZED)

        profile = get_or_create_profile(user)
        tokens = get_tokens_for_user(user)

        data = {
            'user': UserSerializer(user).data,
            'tokens': tokens,
            'api_key': profile.api_key,
        }
        return success_response("Login successful", data)


class LogoutView(APIView):
    """Logout endpoint"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
        except Exception:
            pass
        return success_response("Logout successful")


class UserProfileView(APIView):
    """Get current user's profile"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        profile = get_or_create_profile(request.user)
        serializer = UserProfileSerializer(profile)
        return success_response("Profile fetched successfully", serializer.data)


class UpdateProfileView(APIView):
    """Update user profile"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request):
        serializer = UpdateProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return success_response("Profile updated successfully", UserSerializer(request.user).data)
        return error_response("Profile update failed", serializer.errors)


class ChangePasswordView(APIView):
    """Change user password"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Invalid input", serializer.errors)

        if not request.user.check_password(serializer.validated_data['current_password']):
            return error_response("Current password is incorrect")

        request.user.set_password(serializer.validated_data['new_password'])
        request.user.save()

        tokens = get_tokens_for_user(request.user)
        return success_response("Password changed successfully", {"tokens": tokens})


class RegenerateAPIKeyView(APIView):
    """Regenerate user's API key"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        profile = get_or_create_profile(request.user)
        new_key = profile.regenerate_api_key()
        return success_response("API key regenerated successfully", {"api_key": new_key})


class DeleteAccountView(APIView):
    """Delete user account"""
    permission_classes = [IsAuthenticated]
    
    def delete(self, request):
        password = request.data.get('password', '')
        if not password:
            return error_response("Password confirmation is required")

        if not request.user.check_password(password):
            return error_response("Incorrect password")

        username = request.user.username
        request.user.delete()
        return success_response(f"Account '{username}' has been permanently deleted")


class CheckAuthView(APIView):
    """Check if user is authenticated"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        profile = get_or_create_profile(request.user)
        data = {
            "authenticated": True,
            "user": UserSerializer(request.user).data,
            "api_key": profile.api_key,
        }
        return success_response("User is authenticated", data)


class SearchUsersView(APIView):
    """Search for users to add as team members"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        query = request.GET.get('q', '').strip()
        if not query or len(query) < 2:
            return error_response("Search query must be at least 2 characters")

        users = User.objects.filter(
            Q(username__icontains=query) | Q(email__icontains=query)
        ).exclude(id=request.user.id)[:20]

        results = [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "full_name": f"{user.first_name} {user.last_name}".strip() or user.username
            }
            for user in users
        ]

        data = {
            "query": query,
            "count": len(results),
            "users": results
        }
        return success_response("User search successful", data)
