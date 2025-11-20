# accounts/admin.py
"""
Admin configuration for accounts app
"""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User
from .models import UserProfile


class UserProfileInline(admin.StackedInline):
    """Inline profile editor in User admin"""
    model = UserProfile
    can_delete = False
    verbose_name_plural = 'Profile (New Accounts)'
    readonly_fields = ['api_key', 'created_at', 'updated_at']
    fields = ['api_key', 'bio', 'avatar', 'created_at', 'updated_at']


class NewUserAdmin(BaseUserAdmin):
    """Extended User admin with new profile inline"""
    inlines = (UserProfileInline,)
    list_display = ['username', 'email', 'first_name', 'last_name', 'is_staff', 'get_new_api_key']
    
    def get_new_api_key(self, obj):
        """Display API key from new accounts profile"""
        if hasattr(obj, 'accounts_profile'):
            return obj.accounts_profile.api_key[:20] + '...'
        return 'N/A'
    get_new_api_key.short_description = 'New API Key'


# Don't unregister User yet - we'll do this after full migration
# For now, just register the new UserProfile separately


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    """Admin for new UserProfile model"""
    list_display = ['user', 'api_key_preview', 'created_at', 'updated_at']
    search_fields = ['user__username', 'user__email', 'api_key']
    readonly_fields = ['api_key', 'created_at', 'updated_at']
    fieldsets = (
        ('User', {
            'fields': ('user',)
        }),
        ('API Access', {
            'fields': ('api_key',)
        }),
        ('Profile Info', {
            'fields': ('bio', 'avatar')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def api_key_preview(self, obj):
        """Show truncated API key"""
        return obj.api_key[:20] + '...'
    api_key_preview.short_description = 'API Key'