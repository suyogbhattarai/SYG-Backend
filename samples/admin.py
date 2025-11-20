# samples/admin.py
"""
Admin configuration for samples app
"""

from django.contrib import admin
from .models import SampleBasket


@admin.register(SampleBasket)
class SampleBasketAdmin(admin.ModelAdmin):
    """Admin for new SampleBasket model"""
    list_display = [
        'name',
        'project',
        'uploaded_by',
        'file_size_mb',
        'file_type',
        'uploaded_at'
    ]
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['name', 'project__name', 'uploaded_by__username', 'description']
    readonly_fields = ['uploaded_at', 'file_size', 'file_type']
    
    fieldsets = (
        ('Sample Info', {
            'fields': ('project', 'name', 'description', 'tags')
        }),
        ('File Info', {
            'fields': ('file', 'file_size', 'file_type')
        }),
        ('Upload Info', {
            'fields': ('uploaded_by', 'uploaded_at'),
            'classes': ('collapse',)
        }),
    )
    
    def file_size_mb(self, obj):
        return f"{obj.get_file_size_mb()} MB"
    file_size_mb.short_description = 'File Size'