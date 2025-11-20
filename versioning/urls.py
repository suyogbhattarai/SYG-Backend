# versioning/urls.py - With JWT Endpoints

from django.urls import path
from .views import (
    # User & Auth
    UserProfileView,
    RegenerateAPIKeyView,
    
    # Projects
    ProjectListCreateView,
    ProjectDetailView,
    ProjectVersionsView,
    AllProjectsStatusView,
    
    # Team Management
    ProjectMembersView,
    ProjectMemberDetailView,
    
    # Versions
    VersionUploadView,
    VersionDetailView,
    
    # Push Management
    PushStatusView,
    ApprovePushView,
    RejectPushView,
    CancelPushView,
    
    # Activity
    ProjectActivityLogView,
    
    # Sample Basket
    SampleBasketView,
    SampleDetailView,
)

# Import JWT auth views
from .auth_views import (
    RegisterView,
    LoginView,
    LogoutView,
    ChangePasswordView,
    UpdateProfileView,
    CheckAuthView,
    DeleteAccountView,
    SearchUsersView,
    CustomTokenObtainPairView,
    RefreshTokenView,
)

urlpatterns = [
    # ============================================================================
    # JWT AUTHENTICATION ENDPOINTS (Public)
    # ============================================================================
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('auth/login/', LoginView.as_view(), name='login'),
    path('auth/logout/', LogoutView.as_view(), name='logout'),
    path('auth/check/', CheckAuthView.as_view(), name='check-auth'),
    
    # JWT Token endpoints
    path('auth/token/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/token/refresh/', RefreshTokenView.as_view(), name='token_refresh'),
    
    # ============================================================================
    # USER & AUTH ENDPOINTS (Authenticated)
    # ============================================================================
    path('profile/', UserProfileView.as_view(), name='user-profile'),
    path('profile/update/', UpdateProfileView.as_view(), name='update-profile'),
    path('profile/change-password/', ChangePasswordView.as_view(), name='change-password'),
    path('profile/regenerate-api-key/', RegenerateAPIKeyView.as_view(), name='regenerate-api-key'),
    path('profile/delete-account/', DeleteAccountView.as_view(), name='delete-account'),
    
    # Search users for team collaboration
    path('users/search/', SearchUsersView.as_view(), name='search-users'),
    
    # ============================================================================
    # PROJECT ENDPOINTS
    # ============================================================================
    path('projects/', ProjectListCreateView.as_view(), name='project-list-create'),
    path('projects/<int:project_id>/', ProjectDetailView.as_view(), name='project-detail'),
    path('projects/<int:project_id>/versions/', ProjectVersionsView.as_view(), name='project-versions'),
    path('all_status/', AllProjectsStatusView.as_view(), name='all-projects-status'),
    
    # ============================================================================
    # TEAM MANAGEMENT ENDPOINTS
    # ============================================================================
    path('projects/<int:project_id>/members/', ProjectMembersView.as_view(), name='project-members'),
    path('projects/<int:project_id>/members/<int:member_id>/', ProjectMemberDetailView.as_view(), name='project-member-detail'),
    
    # ============================================================================
    # VERSION ENDPOINTS
    # ============================================================================
    path('versions/<int:version_id>/', VersionDetailView.as_view(), name='version-detail'),
    path('upload_version/', VersionUploadView.as_view(), name='version-upload'),
    
    # ============================================================================
    # PUSH MANAGEMENT ENDPOINTS
    # ============================================================================
    path('push_status/<int:push_id>/', PushStatusView.as_view(), name='push-status'),
    path('push/<int:push_id>/approve/', ApprovePushView.as_view(), name='approve-push'),
    path('push/<int:push_id>/reject/', RejectPushView.as_view(), name='reject-push'),
    path('push/<int:push_id>/cancel/', CancelPushView.as_view(), name='cancel-push'),
    
    # ============================================================================
    # ACTIVITY LOG ENDPOINTS
    # ============================================================================
    path('projects/<int:project_id>/activity/', ProjectActivityLogView.as_view(), name='project-activity'),
    
    # ============================================================================
    # SAMPLE BASKET ENDPOINTS
    # ============================================================================
    path('projects/<int:project_id>/samples/', SampleBasketView.as_view(), name='sample-basket'),
    path('samples/<int:sample_id>/', SampleDetailView.as_view(), name='sample-detail'),
]