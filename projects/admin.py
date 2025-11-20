# projects/admin.py
"""
Admin configuration for projects app
"""

from django.contrib import admin
from .models import Project, ProjectMember


class ProjectMemberInline(admin.TabularInline):
    """Inline member editor in Project admin"""
    model = ProjectMember
    extra = 0
    readonly_fields = ['added_at', 'added_by']
    fields = ['user', 'role', 'added_by', 'added_at']


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    """Admin for new Project model"""
    list_display = [
        'name',
        'owner',
        'version_count',
        'member_count',
        'require_push_approval',
        'created_at'
    ]
    list_filter = ['require_push_approval', 'created_at', 'updated_at']
    search_fields = ['name', 'owner__username', 'description']
    readonly_fields = ['created_at', 'updated_at']
    inlines = [ProjectMemberInline]
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('owner', 'name', 'description')
        }),
        ('Settings', {
            'fields': ('require_push_approval', 'ignore_patterns')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def version_count(self, obj):
        """Display version count"""
        return obj.get_version_count()
    version_count.short_description = 'Versions'
    
    def member_count(self, obj):
        """Display member count"""
        return obj.members_new.count()
    member_count.short_description = 'Members'


@admin.register(ProjectMember)
class ProjectMemberAdmin(admin.ModelAdmin):
    """Admin for new ProjectMember model"""
    list_display = ['user', 'project', 'role', 'added_by', 'added_at']
    list_filter = ['role', 'added_at']
    search_fields = ['user__username', 'project__name']
    readonly_fields = ['added_at']
    
    fieldsets = (
        ('Member Info', {
            'fields': ('project', 'user', 'role')
        }),
        ('Meta', {
            'fields': ('added_by', 'added_at'),
            'classes': ('collapse',)
        }),
    )