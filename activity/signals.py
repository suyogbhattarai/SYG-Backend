# activity/signals.py
"""
Signal handlers for activity app
This app listens to signals from other apps and creates activity logs
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

# Import models from other apps
from projects.models import Project, ProjectMember
from versions.models import Version, PendingPush
from samples.models import SampleBasket
from .models import ActivityLog


# ============================================================================
# PROJECT SIGNALS
# ============================================================================

@receiver(post_save, sender=Project)
def log_project_created(sender, instance, created, **kwargs):
    """Log project creation"""
    if created:
        ActivityLog.log(
            project=instance,
            user=instance.owner,
            action='project_created',
            description=f'Project "{instance.name}" was created',
            metadata={'project_name': instance.name}
        )


# ============================================================================
# PROJECT MEMBER SIGNALS
# ============================================================================

@receiver(post_save, sender=ProjectMember)
def log_member_added(sender, instance, created, **kwargs):
    """Log when member is added"""
    if created:
        ActivityLog.log(
            project=instance.project,
            user=instance.added_by,
            action='member_added',
            description=f'{instance.user.username} was added as {instance.get_role_display()}',
            metadata={
                'member_username': instance.user.username,
                'role': instance.role
            }
        )


@receiver(post_delete, sender=ProjectMember)
def log_member_removed(sender, instance, **kwargs):
    """Log when member is removed"""
    ActivityLog.log(
        project=instance.project,
        user=instance.added_by,  # Best approximation
        action='member_removed',
        description=f'{instance.user.username} was removed from the project',
        metadata={'member_username': instance.user.username}
    )


# ============================================================================
# VERSION SIGNALS
# ============================================================================

@receiver(post_save, sender=Version)
def log_version_created(sender, instance, created, **kwargs):
    """Log version creation"""
    if created and instance.created_by and instance.file:
        ActivityLog.log(
            project=instance.project,
            user=instance.created_by,
            action='version_pushed',
            description=f'New version pushed: {instance.commit_message or "No message"}',
            metadata={
                'version_id': instance.id,
                'commit_message': instance.commit_message,
                'file_size_mb': instance.get_file_size_mb()
            }
        )


# ============================================================================
# SAMPLE SIGNALS
# ============================================================================

@receiver(post_save, sender=SampleBasket)
def log_sample_uploaded(sender, instance, created, **kwargs):
    """Log sample upload"""
    if created:
        ActivityLog.log(
            project=instance.project,
            user=instance.uploaded_by,
            action='sample_uploaded',
            description=f'Uploaded sample: {instance.name}',
            metadata={
                'sample_id': instance.id,
                'sample_name': instance.name,
                'file_type': instance.file_type
            }
        )