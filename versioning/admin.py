# versioning/admin.py

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import (
    UserProfile, Project, ProjectMember, Version,
    PendingPush, ActivityLog, SampleBasket
)


# Inline admin for UserProfile
class UserProfileInline(admin.StackedInline):
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile'
    readonly_fields = ['api_key', 'created_at', 'updated_at']


# Extended User Admin
class UserAdmin(BaseUserAdmin):
    inlines = (UserProfileInline,)
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'get_api_key']
    
    def get_api_key(self, obj):
        return obj.profile.api_key[:20] + '...' if hasattr(obj, 'profile') else 'N/A'
    get_api_key.short_description = 'API Key'


# Unregister default User admin and register extended one
admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'api_key_preview', 'created_at']
    search_fields = ['user__username', 'user__email', 'api_key']
    readonly_fields = ['api_key', 'created_at', 'updated_at']
    
    def api_key_preview(self, obj):
        return obj.api_key[:20] + '...'
    api_key_preview.short_description = 'API Key'


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'version_count', 'require_push_approval', 'created_at']
    list_filter = ['require_push_approval', 'created_at', 'updated_at']
    search_fields = ['name', 'owner__username', 'description']
    readonly_fields = ['created_at', 'updated_at']
    
    def version_count(self, obj):
        return obj.versions.count()
    version_count.short_description = 'Versions'


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    list_display = ['user', 'project', 'role', 'added_by', 'added_at']
    list_filter = ['role', 'added_at']
    search_fields = ['user__username', 'project__name']
    readonly_fields = ['added_at']


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    list_display = ['get_version_display', 'project', 'created_by', 'file_size_mb', 'file_count', 'created_at']
    list_filter = ['created_at', 'project']
    search_fields = ['project__name', 'created_by__username', 'commit_message', 'hash']
    readonly_fields = ['created_at', 'hash']
    
    def get_version_display(self, obj):
        return f"v{obj.get_version_number()}"
    get_version_display.short_description = 'Version'
    
    def file_size_mb(self, obj):
        return f"{obj.get_file_size_mb()} MB"
    file_size_mb.short_description = 'File Size'


@admin.register(PendingPush)
class PendingPushAdmin(admin.ModelAdmin):
    list_display = ['id', 'project', 'created_by', 'status', 'progress', 'created_at', 'requires_approval']
    list_filter = ['status', 'created_at']
    search_fields = ['project__name', 'created_by__username', 'commit_message']
    readonly_fields = ['created_at', 'completed_at', 'approved_at']
    
    def requires_approval(self, obj):
        return obj.project.require_push_approval and obj.created_by != obj.project.owner
    requires_approval.boolean = True
    requires_approval.short_description = 'Needs Approval'


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ['project', 'user', 'action', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['project__name', 'user__username', 'description']
    readonly_fields = ['created_at']
    
    def has_add_permission(self, request):
        # Logs are created automatically
        return False


@admin.register(SampleBasket)
class SampleBasketAdmin(admin.ModelAdmin):
    list_display = ['name', 'project', 'uploaded_by', 'file_size_mb', 'file_type', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['name', 'project__name', 'uploaded_by__username', 'description']
    readonly_fields = ['uploaded_at', 'file_size']
    
    def file_size_mb(self, obj):
        return f"{obj.get_file_size_mb()} MB"
    file_size_mb.short_description = 'File Size'