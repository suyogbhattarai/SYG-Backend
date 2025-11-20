# activity/models.py
"""
Activity logging models
Tracks all project activities and changes
"""

from django.db import models
from django.contrib.auth.models import User
from projects.models import Project


def sanitize_text(text):
    """Remove null characters and other problematic characters from text"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


class ActivityLog(models.Model):
    """
    Track all project activities
    This is a NEW model that will eventually replace versioning.ActivityLog
    """
    ACTION_CHOICES = [
        ('project_created', 'Project Created'),
        ('member_added', 'Member Added'),
        ('member_removed', 'Member Removed'),
        ('member_role_changed', 'Member Role Changed'),
        ('version_pushed', 'Version Pushed'),
        ('version_deleted', 'Version Deleted'),
        ('push_approved', 'Push Approved'),
        ('push_rejected', 'Push Rejected'),
        ('settings_changed', 'Settings Changed'),
        ('sample_uploaded', 'Sample Uploaded'),
        ('sample_deleted', 'Sample Deleted'),
    ]
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='activity_logs_new'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='activities_new'
    )
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.TextField()
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Activity Log (New)'
        verbose_name_plural = 'Activity Logs (New)'
        db_table = 'activity_activitylog'
        indexes = [
            models.Index(fields=['-created_at']),
            models.Index(fields=['project', '-created_at']),
            models.Index(fields=['user', '-created_at']),
        ]
    
    def __str__(self):
        user_name = self.user.username if self.user else 'System'
        return f"{self.project} - {self.action} by {user_name} (New)"
    
    def save(self, *args, **kwargs):
        if self.description:
            self.description = sanitize_text(self.description)
        super().save(*args, **kwargs)
    
    @staticmethod
    def log(project, user, action, description, metadata=None):
        """Helper method to create activity logs"""
        return ActivityLog.objects.create(
            project=project,
            user=user,
            action=action,
            description=sanitize_text(description),
            metadata=metadata
        )