"""
=============================================================================
FILE 2: versions/admin.py
=============================================================================
Django admin configuration for versions app
Updated to properly show snapshot vs CAS storage
"""

from django.contrib import admin
from django.utils.html import format_html
from .models import Version, PendingPush, DownloadRequest, FileBlob


@admin.register(FileBlob)
class FileBlobAdmin(admin.ModelAdmin):
    """Admin for FileBlob model"""
    list_display = ('hash_short', 'size_display', 'ref_count', 'created_at')
    list_filter = ('created_at', 'ref_count')
    search_fields = ('hash',)
    readonly_fields = ('hash', 'size', 'ref_count', 'created_at', 'file')
    
    def hash_short(self, obj):
        """Display shortened hash"""
        return obj.hash[:16] + '...'
    hash_short.short_description = 'Hash'
    
    def size_display(self, obj):
        """Display size in MB"""
        return f"{obj.get_size_mb()} MB"
    size_display.short_description = 'Size'


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    """Admin for Version model"""
    list_display = ('id', 'project', 'version_number_display', 'status_badge', 'storage_type_display', 'file_count', 'created_by', 'created_at')
    list_filter = ('status', 'is_snapshot', 'created_at', 'project')
    search_fields = ('project__name', 'hash', 'commit_message', 'created_by__username')
    readonly_fields = ('hash', 'created_at', 'completed_at', 'manifest_file_path_display', 'snapshot_file_display')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('project', 'created_by', 'commit_message', 'status')
        }),
        ('Storage', {
            'fields': ('is_snapshot', 'file', 'snapshot_file_display', 'manifest_file_path_display', 'hash')
        }),
        ('Metrics', {
            'fields': ('file_size', 'file_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def version_number_display(self, obj):
        """Display version number"""
        num = obj.get_version_number()
        return f'v{num}' if num else 'N/A'
    version_number_display.short_description = 'Version'
    
    def status_badge(self, obj):
        """Display status with color badge"""
        colors = {
            'completed': 'green',
            'processing': 'orange',
            'pending': 'blue',
            'failed': 'red',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def storage_type_display(self, obj):
        """Display storage type"""
        if obj.is_snapshot:
            return format_html('<strong style="color: blue;">Full Snapshot ZIP</strong>')
        return format_html('<span style="color: green;">CAS Manifest</span>')
    storage_type_display.short_description = 'Storage'
    
    def snapshot_file_display(self, obj):
        """Display snapshot file info"""
        if obj.is_snapshot and obj.file:
            return format_html(
                '<a href="{}" target="_blank">Download Snapshot</a> ({} MB)',
                obj.file.url,
                obj.get_file_size_mb()
            )
        return 'N/A (CAS Version)'
    snapshot_file_display.short_description = 'Snapshot File'
    
    def manifest_file_path_display(self, obj):
        """Display manifest file path"""
        if not obj.is_snapshot and obj.manifest_file_path:
            return format_html(
                '<code style="word-break: break-all; background-color: #f5f5f5; padding: 5px; border-radius: 3px;">{}</code>',
                obj.manifest_file_path
            )
        return 'N/A (Snapshot Version)'
    manifest_file_path_display.short_description = 'Manifest File Path'


@admin.register(PendingPush)
class PendingPushAdmin(admin.ModelAdmin):
    """Admin for PendingPush model"""
    list_display = ('id', 'project', 'created_by', 'status_badge', 'progress', 'version_info', 'created_at')
    list_filter = ('status', 'created_at', 'project')
    search_fields = ('project__name', 'created_by__username', 'commit_message')
    readonly_fields = ('created_at', 'completed_at', 'approved_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('project', 'created_by', 'commit_message', 'status', 'progress', 'message')
        }),
        ('Version', {
            'fields': ('version',)
        }),
        ('Approval', {
            'fields': ('approved_by', 'approved_at', 'rejection_reason'),
            'classes': ('collapse',)
        }),
        ('Error Details', {
            'fields': ('error_details',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def status_badge(self, obj):
        """Display status with color badge"""
        colors = {
            'done': 'green',
            'processing': 'orange',
            'pending': 'blue',
            'awaiting_approval': 'purple',
            'approved': 'lightblue',
            'failed': 'red',
            'rejected': 'darkred',
            'cancelled': 'gray',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def version_info(self, obj):
        """Display version info"""
        if obj.version:
            num = obj.version.get_version_number()
            version_str = f'v{num}' if num else f'#{obj.version.id}'
            status_str = f'[{obj.version.status}]'
            storage_type = '📦 Snapshot' if obj.version.is_snapshot else '🔗 CAS'
            return f'{version_str} {status_str} {storage_type}'
        return 'N/A'
    version_info.short_description = 'Version'


@admin.register(DownloadRequest)
class DownloadRequestAdmin(admin.ModelAdmin):
    """Admin for DownloadRequest model"""
    list_display = ('id', 'version_info', 'requested_by', 'status_badge', 'progress', 'file_size_mb_display', 'created_at')
    list_filter = ('status', 'created_at')
    search_fields = ('version__project__name', 'requested_by__username')
    readonly_fields = ('created_at', 'completed_at', 'expires_at', 'file_size')
    
    fieldsets = (
        ('Request Info', {
            'fields': ('version', 'requested_by', 'status', 'progress', 'message')
        }),
        ('File', {
            'fields': ('zip_file', 'file_size')
        }),
        ('Error', {
            'fields': ('error_details',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at', 'expires_at'),
            'classes': ('collapse',)
        }),
    )
    
    def version_info(self, obj):
        """Display version info"""
        num = obj.version.get_version_number()
        version_str = f'v{num}' if num else f'#{obj.version.id}'
        return f'{obj.version.project.name} {version_str}'
    version_info.short_description = 'Version'
    
    def status_badge(self, obj):
        """Display status with color badge"""
        colors = {
            'completed': 'green',
            'processing': 'orange',
            'pending': 'blue',
            'failed': 'red',
            'expired': 'gray',
        }
        color = colors.get(obj.status, 'gray')
        return format_html(
            '<span style="background-color: {}; color: white; padding: 3px 10px; border-radius: 3px;">{}</span>',
            color,
            obj.get_status_display()
        )
    status_badge.short_description = 'Status'
    
    def file_size_mb_display(self, obj):
        """Display file size in MB"""
        if obj.file_size:
            return f'{round(obj.file_size / (1024 * 1024), 2)} MB'
        return 'N/A'
    file_size_mb_display.short_description = 'File Size'