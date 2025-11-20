# accounts/signals.py
"""
Signal handlers for accounts app
"""

from django.db.models.signals import post_save
from django.dispatch import receiver
from django.contrib.auth.models import User
from .models import UserProfile


@receiver(post_save, sender=User)
def create_new_user_profile(sender, instance, created, **kwargs):
    """
    Automatically create NEW UserProfile when User is created
    Only creates if it doesn't already exist
    """
    if created:
        # Check if profile already exists (might have been created manually)
        if not hasattr(instance, 'accounts_profile'):
            UserProfile.objects.create(
                user=instance,
                api_key=UserProfile.generate_api_key()
            )


@receiver(post_save, sender=User)
def save_new_user_profile(sender, instance, **kwargs):
    """
    Save NEW UserProfile when User is saved
    """
    if hasattr(instance, 'accounts_profile'):
        instance.accounts_profile.save()