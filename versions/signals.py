# ============================================================================
# SIGNALS
# ============================================================================

"""
versions/signals.py
Signal handlers for versions app
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Version, PendingPush


@receiver(post_save, sender=Version)
def log_version_created(sender, instance, created, **kwargs):
    """
    Log version creation
    Will implement activity logging when activity app is created
    """
    if created and instance.created_by:
        # TODO: Log activity when activity app is ready
        # ActivityLog.log(
        #     project=instance.project,
        #     user=instance.created_by,
        #     action='version_pushed',
        #     description=f'New version pushed: {instance.commit_message or "No message"}'
        # )
        pass


@receiver(post_save, sender=PendingPush)
def log_push_status_change(sender, instance, created, **kwargs):
    """
    Log push status changes
    Will implement activity logging when activity app is created
    """
    if not created and instance.status in ['approved', 'rejected']:
        # TODO: Log activity when activity app is ready
        pass