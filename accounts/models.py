# accounts/models.py
"""
User profile and authentication models
Handles user accounts, API keys, and profile information
"""

from django.db import models
from django.contrib.auth.models import User
from django.utils.crypto import get_random_string


def sanitize_text(text):
    """Remove null characters and other problematic characters from text"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


class UserProfile(models.Model):
    """
    Extended user profile with API key
    This is a NEW model that will eventually replace versioning.UserProfile
    """
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='accounts_profile'  # Different related_name to avoid conflict
    )
    api_key = models.CharField(max_length=64, unique=True, db_index=True)
    bio = models.TextField(null=True, blank=True)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = 'User Profile (New)'
        verbose_name_plural = 'User Profiles (New)'
        db_table = 'accounts_userprofile'  # Explicit table name
    
    def __str__(self):
        return f"{self.user.username}'s Profile (New)"
    
    @staticmethod
    def generate_api_key():
        """Generate a unique API key"""
        return get_random_string(64)
    
    def regenerate_api_key(self):
        """Regenerate API key for this user"""
        self.api_key = self.generate_api_key()
        self.save()
        return self.api_key
    
    def save(self, *args, **kwargs):
        if self.bio:
            self.bio = sanitize_text(self.bio)
        super().save(*args, **kwargs)