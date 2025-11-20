# samples/signals.py
"""
Signal handlers for samples app
"""

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from .models import SampleBasket


@receiver(post_save, sender=SampleBasket)
def log_sample_uploaded(sender, instance, created, **kwargs):
    """
    Log sample upload
    Will implement activity logging when activity app is created
    """
    if created:
        # TODO: Log activity when activity app is ready
        # ActivityLog.log(
        #     project=instance.project,
        #     user=instance.uploaded_by,
        #     action='sample_uploaded',
        #     description=f'Uploaded sample: {instance.name}'
        # )
        pass


@receiver(post_delete, sender=SampleBasket)
def log_sample_deleted(sender, instance, **kwargs):
    """
    Log sample deletion
    Will implement activity logging when activity app is created
    """
    # TODO: Log activity when activity app is ready
    # ActivityLog.log(
    #     project=instance.project,
    #     user=...,  # Need to get from request
    #     action='sample_deleted',
    #     description=f'Deleted sample: {instance.name}'
    # )
    pass