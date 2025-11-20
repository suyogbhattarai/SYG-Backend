# samples/models.py
"""
Sample basket models
Handles sample file uploads and management
"""

import os
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import pre_delete
from django.dispatch import receiver
from projects.models import Project


def sanitize_text(text):
    """Remove null characters and other problematic characters from text"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


def sample_upload_path(instance, filename):
    """Generate upload path for sample files"""
    return os.path.join(
        'samples',
        instance.project.owner.username,
        instance.project.name,
        filename
    )


class SampleBasket(models.Model):
    """
    Sample files uploaded to project
    This is a NEW model that will eventually replace versioning.SampleBasket
    """
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='samples_new'
    )
    uploaded_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='samples_uploaded_new'
    )
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to=sample_upload_path)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_type = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
        verbose_name = 'Sample (New)'
        verbose_name_plural = 'Samples (New)'
        db_table = 'samples_samplebasket'
        indexes = [
            models.Index(fields=['project', '-uploaded_at']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.project} (New)"
    
    def save(self, *args, **kwargs):
        if self.name:
            self.name = sanitize_text(self.name)
        if self.description:
            self.description = sanitize_text(self.description)
        
        # Auto-set file size if not set
        if not self.file_size and self.file:
            try:
                self.file_size = self.file.size
            except:
                pass
        
        # Auto-detect file type from extension
        if not self.file_type and self.file:
            try:
                _, ext = os.path.splitext(self.file.name)
                self.file_type = ext.lower().replace('.', '')
            except:
                pass
        
        super().save(*args, **kwargs)
    
    def get_file_size_mb(self):
        """Get file size in megabytes"""
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0
    
    def delete(self, *args, **kwargs):
        """Override delete to remove file from storage"""
        # Delete the file from storage
        if self.file:
            try:
                if os.path.isfile(self.file.path):
                    os.remove(self.file.path)
                    print(f"Deleted sample file: {self.file.path}")
            except Exception as e:
                print(f"Error deleting sample file: {e}")
        
        super().delete(*args, **kwargs)


# Signal handlers for file cleanup
@receiver(pre_delete, sender=SampleBasket)
def sample_basket_pre_delete(sender, instance, **kwargs):
    """Delete file from storage before model deletion"""
    if instance.file:
        try:
            if os.path.isfile(instance.file.path):
                os.remove(instance.file.path)
                print(f"Signal: Deleted sample file: {instance.file.path}")
        except Exception as e:
            print(f"Signal: Error deleting sample file: {e}")