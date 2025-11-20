# versioning/auth_views.py - JWT Version

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.db import IntegrityError
from .models import UserProfile
import re


def sanitize_string(s):
    """Remove null characters and other problematic characters"""
    if not isinstance(s, str):
        return s
    return ''.join(char for char in s if ord(char) >= 32 or char in '\n\r\t')


def validate_email(email):
    """Validate email format"""
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


def validate_password(password):
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not re.search(r'[A-Z]', password):
        return False, "Password must contain at least one uppercase letter"
    if not re.search(r'[a-z]', password):
        return False, "Password must contain at least one lowercase letter"
    if not re.search(r'[0-9]', password):
        return False, "Password must contain at least one number"
    return True, "Password is valid"


def get_tokens_for_user(user):
    """Generate JWT tokens for user"""
    refresh = RefreshToken.for_user(user)
    return {
        'refresh': str(refresh),
        'access': str(refresh.access_token),
    }


# Custom Token Serializer with additional user info
class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        
        # Add custom claims
        token['username'] = user.username
        token['email'] = user.email
        
        return token
    
    def validate(self, attrs):
        data = super().validate(attrs)
        
        # Add extra responses
        data['user'] = {
            'id': self.user.id,
            'username': self.user.username,
            'email': self.user.email,
            'first_name': self.user.first_name,
            'last_name': self.user.last_name,
        }
        
        # Add API key (for backward compatibility with existing plugin code)
        if hasattr(self.user, 'profile'):
            data['api_key'] = self.user.profile.api_key
        
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer


class RegisterView(APIView):
    """User registration endpoint with JWT tokens"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        username = sanitize_string(request.data.get('username', '').strip())
        email = sanitize_string(request.data.get('email', '').strip())
        password = request.data.get('password', '')
        first_name = sanitize_string(request.data.get('first_name', '').strip())
        last_name = sanitize_string(request.data.get('last_name', '').strip())
        
        # Validation
        if not username:
            return Response({'error': 'Username is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not email:
            return Response({'error': 'Email is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not password:
            return Response({'error': 'Password is required'}, status=status.HTTP_400_BAD_REQUEST)
        
        if not re.match(r'^[a-zA-Z0-9_-]{3,30}$', username):
            return Response(
                {'error': 'Username must be 3-30 characters and contain only letters, numbers, hyphens, and underscores'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not validate_email(email):
            return Response({'error': 'Invalid email format'}, status=status.HTTP_400_BAD_REQUEST)
        
        is_valid, message = validate_password(password)
        if not is_valid:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(username=username).exists():
            return Response({'error': 'Username already exists'}, status=status.HTTP_400_BAD_REQUEST)
        
        if User.objects.filter(email=email).exists():
            return Response({'error': 'Email already registered'}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                first_name=first_name,
                last_name=last_name
            )
            
            user.refresh_from_db()
            
            # Generate JWT tokens
            tokens = get_tokens_for_user(user)
            
            return Response({
                'message': 'Registration successful',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                },
                'tokens': tokens,
                'api_key': user.profile.api_key,  # For backward compatibility
            }, status=status.HTTP_201_CREATED)
            
        except IntegrityError:
            return Response({'error': 'Registration failed. Please try again.'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'Registration failed: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class LoginView(APIView):
    """User login endpoint with JWT tokens"""
    permission_classes = [AllowAny]
    
    def post(self, request):
        username = sanitize_string(request.data.get('username', '').strip())
        password = request.data.get('password', '')
        
        if not username or not password:
            return Response(
                {'error': 'Username and password are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        user = authenticate(request, username=username, password=password)
        
        if user is not None:
            # Ensure user has a profile
            if not hasattr(user, 'profile'):
                UserProfile.objects.create(
                    user=user,
                    api_key=UserProfile.generate_api_key()
                )
                user.refresh_from_db()
            
            # Generate JWT tokens
            tokens = get_tokens_for_user(user)
            
            return Response({
                'message': 'Login successful',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                },
                'tokens': tokens,
                'api_key': user.profile.api_key,  # For backward compatibility
            }, status=status.HTTP_200_OK)
        else:
            return Response(
                {'error': 'Invalid username or password'},
                status=status.HTTP_401_UNAUTHORIZED
            )


class LogoutView(APIView):
    """
    Logout endpoint - blacklist refresh token
    For JWT, client should just delete the token
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        try:
            refresh_token = request.data.get("refresh")
            if refresh_token:
                token = RefreshToken(refresh_token)
                token.blacklist()
            
            return Response({
                'message': 'Logout successful. Please delete your access token.'
            }, status=status.HTTP_200_OK)
        except Exception:
            return Response({
                'message': 'Logout successful. Please delete your access token.'
            }, status=status.HTTP_200_OK)


class ChangePasswordView(APIView):
    """Change user password"""
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        current_password = request.data.get('current_password', '')
        new_password = request.data.get('new_password', '')
        confirm_password = request.data.get('confirm_password', '')
        
        if not current_password or not new_password or not confirm_password:
            return Response(
                {'error': 'All password fields are required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if new_password != confirm_password:
            return Response(
                {'error': 'New passwords do not match'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        is_valid, message = validate_password(new_password)
        if not is_valid:
            return Response({'error': message}, status=status.HTTP_400_BAD_REQUEST)
        
        if not request.user.check_password(current_password):
            return Response(
                {'error': 'Current password is incorrect'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        request.user.set_password(new_password)
        request.user.save()
        
        # Generate new tokens after password change
        tokens = get_tokens_for_user(request.user)
        
        return Response({
            'message': 'Password changed successfully',
            'tokens': tokens  # Return new tokens
        }, status=status.HTTP_200_OK)


class UpdateProfileView(APIView):
    """Update user profile information"""
    permission_classes = [IsAuthenticated]
    
    def put(self, request):
        user = request.user
        
        email = sanitize_string(request.data.get('email', '').strip())
        first_name = sanitize_string(request.data.get('first_name', '').strip())
        last_name = sanitize_string(request.data.get('last_name', '').strip())
        
        if email:
            if not validate_email(email):
                return Response({'error': 'Invalid email format'}, status=status.HTTP_400_BAD_REQUEST)
            
            if User.objects.filter(email=email).exclude(id=user.id).exists():
                return Response({'error': 'Email already in use'}, status=status.HTTP_400_BAD_REQUEST)
            
            user.email = email
        
        if first_name:
            user.first_name = first_name
        
        if last_name:
            user.last_name = last_name
        
        user.save()
        
        return Response({
            'message': 'Profile updated successfully',
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        }, status=status.HTTP_200_OK)


class CheckAuthView(APIView):
    """Check if JWT token is valid"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        user = request.user
        return Response({
            'authenticated': True,
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            },
            'api_key': user.profile.api_key if hasattr(user, 'profile') else None
        }, status=status.HTTP_200_OK)


class RefreshTokenView(TokenRefreshView):
    """
    Refresh access token using refresh token
    Built-in view from djangorestframework-simplejwt
    """
    pass


class DeleteAccountView(APIView):
    """Delete user account"""
    permission_classes = [IsAuthenticated]
    
    def delete(self, request):
        password = request.data.get('password', '')
        
        if not password:
            return Response(
                {'error': 'Password confirmation is required'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        if not request.user.check_password(password):
            return Response({'error': 'Incorrect password'}, status=status.HTTP_400_BAD_REQUEST)
        
        username = request.user.username
        request.user.delete()
        
        return Response({
            'message': f'Account {username} has been permanently deleted'
        }, status=status.HTTP_200_OK)


class SearchUsersView(APIView):
    """Search for users to add as team members"""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        query = sanitize_string(request.GET.get('q', '').strip())
        
        if not query or len(query) < 2:
            return Response(
                {'error': 'Search query must be at least 2 characters'},
                status=status.HTTP_400_BAD_REQUEST
            )
        
        users = User.objects.filter(
            username__icontains=query
        ) | User.objects.filter(
            email__icontains=query
        )
        
        users = users.exclude(id=request.user.id)[:20]
        
        results = [
            {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'full_name': f"{user.first_name} {user.last_name}".strip() or user.username
            }
            for user in users
        ]
        
        return Response({
            'query': query,
            'count': len(results),
            'users': results
        }, status=status.HTTP_200_OK)