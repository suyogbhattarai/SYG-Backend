# activity/admin.py
"""
Admin configuration for activity app
"""

from django.contrib import admin
from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Admin for new ActivityLog model"""
    list_display = ['project', 'user', 'action', 'short_description', 'created_at']
    list_filter = ['action', 'created_at']
    search_fields = ['project__name', 'user__username', 'description']
    readonly_fields = ['created_at']
    date_hierarchy = 'created_at'
    
    fieldsets = (
        ('Activity Info', {
            'fields': ('project', 'user', 'action', 'description')
        }),
        ('Metadata', {
            'fields': ('metadata',),
            'classes': ('collapse',)
        }),
        ('Timestamp', {
            'fields': ('created_at',)
        }),
    )
    
    def short_description(self, obj):
        """Show truncated description"""
        if len(obj.description) > 50:
            return obj.description[:50] + '...'
        return obj.description
    short_description.short_description = 'Description'
    
    def has_add_permission(self, request):
        """Logs are created automatically"""
        return False
    
    def has_change_permission(self, request, obj=None):
        """Logs should not be edited"""
        return False