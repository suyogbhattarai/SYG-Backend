"""
=============================================================================
FILE: versions/admin.py
=============================================================================
Django admin configuration for versions app
FIXED: Enhanced display with readable username_userid:projectname_projectuid format
"""

from django.contrib import admin
from django.utils.html import format_html
from django.db.models import Count
from .models import Version, PendingPush, DownloadRequest, FileBlob, BlobReference


@admin.register(FileBlob)
class FileBlobAdmin(admin.ModelAdmin):
    """Admin for FileBlob model with blob reference info"""
    list_display = ('hash_short', 'size_display', 'ref_count', 'reference_count_display', 'projects_using_display', 'created_at')
    list_filter = ('created_at', 'ref_count')
    search_fields = ('hash',)
    readonly_fields = ('hash', 'size', 'ref_count', 'created_at', 'file', 'blob_references_info')
    
    fieldsets = (
        ('Blob Info', {
            'fields': ('hash', 'size', 'ref_count', 'created_at', 'file')
        }),
        ('Cross-Project Usage', {
            'fields': ('blob_references_info',),
            'description': 'Shows all projects and versions using this blob'
        }),
    )
    
    def hash_short(self, obj):
        """Display shortened hash"""
        return obj.hash[:16] + '...'
    hash_short.short_description = 'Hash'
    
    def size_display(self, obj):
        """Display size in MB"""
        return f"{obj.get_size_mb()} MB"
    size_display.short_description = 'Size'
    
    def reference_count_display(self, obj):
        """Display actual reference count"""
        actual_count = obj.get_reference_count()
        if actual_count == 0:
            return format_html('<span style="color: red;">No references</span>')
        elif actual_count == 1:
            return format_html('<span style="color: blue;">1 reference</span>')
        else:
            return format_html('<span style="color: green; font-weight: bold;">{} references</span>', actual_count)
    reference_count_display.short_description = 'Active References'
    
    def projects_using_display(self, obj):
        """Display projects using this blob with readable format"""
        refs = BlobReference.objects.filter(blob=obj).values('project').distinct()
        project_count = refs.count()
        
        if project_count == 0:
            return format_html('<span style="color: red;">❌ Not used</span>')
        elif project_count == 1:
            ref = BlobReference.objects.filter(blob=obj).select_related('project', 'project__owner').first()
            if ref:
                username = ref.project.owner.username if ref.project.owner else 'Unknown'
                user_id = ref.project.owner.id if ref.project.owner else 'N/A'
                projectname = ref.project.name
                project_uid = ref.project.uid[:8]
                return format_html(
                    '<span style="color: green;">✓ {}_{}:{}</span><br><small style="color: #666;">UID: {}...</small>',
                    username, user_id, projectname, project_uid
                )
            return format_html('<span style="color: green;">✓ 1 project</span>')
        else:
            return format_html(
                '<span style="color: green; font-weight: bold;">✓ {} projects</span>',
                project_count
            )
    projects_using_display.short_description = 'Projects Using'
    
    def blob_references_info(self, obj):
        """Display detailed blob reference information with readable format"""
        refs = BlobReference.objects.filter(blob=obj).select_related('project', 'project__owner', 'version')
        
        if not refs.exists():
            return format_html('<span style="color: red;">No active references</span>')
        
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += '<tr style="background-color: #f0f0f0;">'
        html += '<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">User</th>'
        html += '<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Project</th>'
        html += '<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Version</th>'
        html += '<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Created</th>'
        html += '</tr>'
        
        for ref in refs:
            version_num = ref.version.version_number if ref.version.version_number else f'#{ref.version.id}'
            username = ref.project.owner.username if ref.project.owner else 'Unknown'
            user_id = ref.project.owner.id if ref.project.owner else 'N/A'
            projectname = ref.project.name
            project_uid = ref.project.uid[:8]
            created = ref.created_at.strftime('%Y-%m-%d %H:%M')
            
            html += '<tr style="border-bottom: 1px solid #ddd;">'
            html += f'<td style="border: 1px solid #ddd; padding: 8px;"><strong>{username}_{user_id}</strong></td>'
            html += f'<td style="border: 1px solid #ddd; padding: 8px;"><strong>{projectname}</strong><br><small style="color: #666;">UID: {project_uid}...</small></td>'
            html += f'<td style="border: 1px solid #ddd; padding: 8px;">v{version_num}</td>'
            html += f'<td style="border: 1px solid #ddd; padding: 8px;">{created}</td>'
            html += '</tr>'
        
        html += '</table>'
        html += f'<p style="margin-top: 10px; color: green; font-weight: bold;">Total: {refs.count()} active references</p>'
        
        return format_html(html)
    blob_references_info.short_description = 'Active References'


@admin.register(BlobReference)
class BlobReferenceAdmin(admin.ModelAdmin):
    """Admin for BlobReference model - shows blob usage across projects with readable format"""
    list_display = ('id', 'blob_hash_short', 'user_project_display', 'version_display', 'created_at')
    list_filter = ('created_at', 'project')
    search_fields = ('project__name', 'blob__hash', 'project__owner__username', 'project__uid')
    readonly_fields = ('created_at', 'blob_info', 'project_info')
    
    fieldsets = (
        ('Reference Info', {
            'fields': ('blob', 'project', 'version')
        }),
        ('Details', {
            'fields': ('blob_info', 'project_info'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )
    
    def blob_hash_short(self, obj):
        """Display shortened blob hash"""
        return format_html(
            '<code style="background-color: #f5f5f5; padding: 3px 6px; border-radius: 3px;">{}</code>',
            obj.blob.hash[:16] + '...'
        )
    blob_hash_short.short_description = 'Blob Hash'
    
    def user_project_display(self, obj):
        """Display user and project with readable UIDs format"""
        username = obj.project.owner.username if obj.project.owner else 'Unknown'
        user_id = obj.project.owner.id if obj.project.owner else 'N/A'
        projectname = obj.project.name
        project_uid = obj.project.uid[:8]
        
        return format_html(
            '<div style="padding: 5px;">'
            '<strong style="color: #2196F3;">{}_{}:</strong><br>'
            '<strong>{}</strong><br>'
            '<small style="color: #666;">UID: {}...</small>'
            '</div>',
            username,
            user_id,
            projectname,
            project_uid
        )
    user_project_display.short_description = 'User & Project'
    
    def version_display(self, obj):
        """Display version number"""
        version_num = obj.version.version_number if obj.version.version_number else f'#{obj.version.id}'
        status = obj.version.status
        
        status_colors = {
            'completed': 'green',
            'processing': 'orange',
            'pending': 'blue',
            'failed': 'red',
        }
        status_color = status_colors.get(status, 'gray')
        
        return format_html(
            'v{} <span style="background-color: {}; color: white; padding: 2px 6px; border-radius: 3px; font-size: 11px; margin-left: 5px;">{}</span>',
            version_num,
            status_color,
            status
        )
    version_display.short_description = 'Version'
    
    def blob_info(self, obj):
        """Display detailed blob information"""
        blob = obj.blob
        other_refs = BlobReference.objects.filter(blob=blob).exclude(id=obj.id).count()
        
        return format_html(
            '<div style="background-color: #f9f9f9; padding: 10px; border-radius: 5px; border-left: 4px solid #4CAF50;">'
            '<strong>Hash:</strong> <code>{}</code><br>'
            '<strong>Size:</strong> {} MB<br>'
            '<strong>Ref Count:</strong> {}<br>'
            '<strong>Created:</strong> {}<br>'
            '<strong>Other References:</strong> {} other projects/versions<br>'
            '<strong>Safe to Delete:</strong> <span style="color: {}; font-weight: bold;">{}</span>'
            '</div>',
            blob.hash,
            blob.get_size_mb(),
            blob.ref_count,
            blob.created_at.strftime('%Y-%m-%d %H:%M:%S'),
            other_refs,
            'red' if other_refs > 0 else 'green',
            'NO - Other projects using it' if other_refs > 0 else 'YES - No other references'
        )
    blob_info.short_description = 'Blob Information'
    
    def project_info(self, obj):
        """Display detailed project information with readable format"""
        project = obj.project
        username = project.owner.username if project.owner else 'Unknown'
        user_id = project.owner.id if project.owner else 'N/A'
        project_uid = project.uid[:8]
        total_refs = BlobReference.objects.filter(project=project).count()
        total_blobs = BlobReference.objects.filter(project=project).values('blob').distinct().count()
        
        return format_html(
            '<div style="background-color: #f0f9ff; padding: 10px; border-radius: 5px; border-left: 4px solid #2196F3;">'
            '<strong>Project:</strong> {}<br>'
            '<strong>Owner:</strong> <span style="color: #2196F3;">{}_{}:</span><br>'
            '<strong>Project UID:</strong> {}...<br>'
            '<strong>Total Blob References:</strong> {}<br>'
            '<strong>Unique Blobs Used:</strong> {}'
            '</div>',
            project.name,
            username,
            user_id,
            project_uid,
            total_refs,
            total_blobs
        )
    project_info.short_description = 'Project Information'


@admin.register(Version)
class VersionAdmin(admin.ModelAdmin):
    """Admin for Version model"""
    list_display = ('id', 'user_project_display', 'version_number_display', 'status_badge', 'storage_type_display', 'file_count', 'blobs_count', 'created_by', 'created_at')
    list_filter = ('status', 'is_snapshot', 'created_at', 'project')
    search_fields = ('project__name', 'hash', 'commit_message', 'created_by__username', 'project__uid', 'uid')
    readonly_fields = ('uid', 'hash', 'created_at', 'completed_at', 'manifest_file_path_display', 'snapshot_file_display', 'blobs_used_display')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('uid', 'project', 'created_by', 'commit_message', 'status')
        }),
        ('Storage', {
            'fields': ('is_snapshot', 'file', 'snapshot_file_display', 'manifest_file_path_display', 'hash')
        }),
        ('Blobs Used', {
            'fields': ('blobs_used_display',),
            'description': 'Shows all blobs referenced by this version'
        }),
        ('Metrics', {
            'fields': ('file_size', 'file_count')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'completed_at'),
            'classes': ('collapse',)
        }),
    )
    
    def user_project_display(self, obj):
        """Display user and project with readable format"""
        username = obj.project.owner.username if obj.project.owner else 'Unknown'
        user_id = obj.project.owner.id if obj.project.owner else 'N/A'
        projectname = obj.project.name
        project_uid = obj.project.uid[:8]
        
        return format_html(
            '<div style="padding: 5px;">'
            '<strong style="color: #2196F3;">{}_{}:</strong><br>'
            '<strong>{}</strong><br>'
            '<small style="color: #666;">UID: {}...</small>'
            '</div>',
            username,
            user_id,
            projectname,
            project_uid
        )
    user_project_display.short_description = 'User & Project'
    
    def version_number_display(self, obj):
        """Display version number"""
        num = obj.version_number
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
            return format_html('<strong style="color: blue;">📦 Full Snapshot ZIP</strong>')
        return format_html('<span style="color: green;">🔗 CAS Manifest</span>')
    storage_type_display.short_description = 'Storage'
    
    def blobs_count(self, obj):
        """Display count of blobs used in this version"""
        blob_count = BlobReference.objects.filter(version=obj).count()
        if blob_count == 0:
            return format_html('<span style="color: gray;">0 blobs</span>')
        else:
            return format_html('<span style="color: green; font-weight: bold;">{} blobs</span>', blob_count)
    blobs_count.short_description = 'Blobs'
    
    def blobs_used_display(self, obj):
        """Display blobs used in this version"""
        refs = BlobReference.objects.filter(version=obj).select_related('blob')
        
        if not refs.exists():
            if obj.is_snapshot:
                return format_html('<span style="color: gray;">Snapshot version - no blob references</span>')
            else:
                return format_html('<span style="color: orange;">No blob references found (inline storage)</span>')
        
        html = '<table style="width: 100%; border-collapse: collapse;">'
        html += '<tr style="background-color: #f0f0f0;">'
        html += '<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Blob Hash</th>'
        html += '<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Size (MB)</th>'
        html += '<th style="border: 1px solid #ddd; padding: 8px; text-align: left;">Other Projects Using</th>'
        html += '</tr>'
        
        total_size = 0
        for ref in refs:
            blob = ref.blob
            other_projects = BlobReference.objects.filter(blob=blob).values('project').distinct().exclude(project=obj.project).count()
            size_mb = blob.get_size_mb()
            total_size += size_mb
            
            other_projects_text = f'{other_projects} other' if other_projects > 0 else '0 (only this project)'
            other_projects_color = 'green' if other_projects > 0 else 'blue'
            
            html += '<tr style="border-bottom: 1px solid #ddd;">'
            html += f'<td style="border: 1px solid #ddd; padding: 8px;"><code>{blob.hash[:16]}...</code></td>'
            html += f'<td style="border: 1px solid #ddd; padding: 8px;">{size_mb}</td>'
            html += f'<td style="border: 1px solid #ddd; padding: 8px; color: {other_projects_color};">{other_projects_text}</td>'
            html += '</tr>'
        
        html += '</table>'
        html += f'<p style="margin-top: 10px; color: green; font-weight: bold;">Total: {refs.count()} blobs, {total_size} MB</p>'
        
        return format_html(html)
    blobs_used_display.short_description = 'Blobs Used'
    
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
    list_display = ('id', 'user_project_display', 'created_by', 'status_badge', 'progress', 'version_info', 'created_at')
    list_filter = ('status', 'created_at', 'project')
    search_fields = ('project__name', 'created_by__username', 'commit_message', 'uid')
    readonly_fields = ('uid', 'created_at', 'completed_at', 'approved_at')
    
    fieldsets = (
        ('Basic Info', {
            'fields': ('uid', 'project', 'created_by', 'commit_message', 'status', 'progress', 'message')
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
    
    def user_project_display(self, obj):
        """Display user and project with readable format"""
        username = obj.project.owner.username if obj.project.owner else 'Unknown'
        user_id = obj.project.owner.id if obj.project.owner else 'N/A'
        projectname = obj.project.name
        project_uid = obj.project.uid[:8]
        
        return format_html(
            '<div style="padding: 5px;">'
            '<strong style="color: #2196F3;">{}_{}:</strong><br>'
            '<strong>{}</strong><br>'
            '<small style="color: #666;">UID: {}...</small>'
            '</div>',
            username,
            user_id,
            projectname,
            project_uid
        )
    user_project_display.short_description = 'User & Project'
    
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
            num = obj.version.version_number if obj.version.version_number else f'#{obj.version.id}'
            version_str = f'v{num}'
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
    search_fields = ('version__project__name', 'requested_by__username', 'uid')
    readonly_fields = ('uid', 'created_at', 'completed_at', 'expires_at', 'file_size')
    
    fieldsets = (
        ('Request Info', {
            'fields': ('uid', 'version', 'requested_by', 'status', 'progress', 'message')
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
        """Display version info with readable format"""
        num = obj.version.version_number if obj.version.version_number else f'#{obj.version.id}'
        username = obj.version.project.owner.username if obj.version.project.owner else 'Unknown'
        user_id = obj.version.project.owner.id if obj.version.project.owner else 'N/A'
        projectname = obj.version.project.name
        project_uid = obj.version.project.uid[:8]
        
        return f'{username}_{user_id}:{projectname}_{project_uid} v{num}'
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