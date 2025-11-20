# versioning/signals.py

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile, Project, ProjectMember, Version, PendingPush, ActivityLog


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Automatically create UserProfile when User is created"""
    if created:
        api_key = UserProfile.generate_api_key()
        UserProfile.objects.create(user=instance, api_key=api_key)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """Save UserProfile when User is saved"""
    if hasattr(instance, 'profile'):
        instance.profile.save()


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


@receiver(post_save, sender=ProjectMember)
def log_member_added(sender, instance, created, **kwargs):
    """Log when member is added"""
    if created:
        ActivityLog.log(
            project=instance.project,
            user=instance.added_by,
            action='member_added',
            description=f'{instance.user.username} was added as {instance.role}',
            metadata={
                'member_username': instance.user.username,
                'role': instance.role
            }
        )


@receiver(post_save, sender=Version)
def log_version_created(sender, instance, created, **kwargs):
    """Log version creation"""
    if created and instance.created_by:
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