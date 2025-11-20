# versioning/models.py

from django.db import models
from django.contrib.auth.models import User
from django.core.validators import RegexValidator
from django.utils.crypto import get_random_string
import os
import json

def project_upload_path(instance, filename):
    return os.path.join('projects', instance.project.owner.username, instance.project.name, filename)

def sample_upload_path(instance, filename):
    return os.path.join('samples', instance.project.owner.username, instance.project.name, filename)

def sanitize_text(text):
    """Remove null characters and other problematic characters from text"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


class UserProfile(models.Model):
    """Extended user profile with API key"""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    api_key = models.CharField(max_length=64, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"{self.user.username}'s Profile"
    
    @staticmethod
    def generate_api_key():
        """Generate a unique API key"""
        return get_random_string(64)
    
    def regenerate_api_key(self):
        """Regenerate API key for this user"""
        self.api_key = self.generate_api_key()
        self.save()
        return self.api_key


class Project(models.Model):
    """Project owned by a user with collaboration support"""
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='owned_projects')
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(null=True, blank=True)
    
    # Collaboration settings
    require_push_approval = models.BooleanField(default=False)
    
    # Ignore patterns (stored as JSON array)
    ignore_patterns = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = [['owner', 'name']]  # Each user can have unique project names

    def __str__(self):
        return f"{self.owner.username}/{self.name}"
    
    def save(self, *args, **kwargs):
        if self.description:
            self.description = sanitize_text(self.description)
        if self.name:
            self.name = sanitize_text(self.name)
        super().save(*args, **kwargs)
    
    def get_version_count(self):
        return self.versions.count()
    
    def get_latest_version(self):
        return self.versions.order_by('-created_at').first()
    
    def has_active_push(self):
        return self.pendingpush_set.filter(
            status__in=['pending', 'processing', 'zipping', 'comparing', 'awaiting_approval']
        ).exists()
    
    def get_user_role(self, user):
        """Get the role of a user in this project"""
        if user == self.owner:
            return 'owner'
        
        member = self.members.filter(user=user).first()
        if member:
            return member.role
        return None
    
    def user_can_edit(self, user):
        """Check if user has edit permission"""
        role = self.get_user_role(user)
        return role in ['owner', 'coproducer']
    
    def user_can_view(self, user):
        """Check if user has view permission"""
        role = self.get_user_role(user)
        return role in ['owner', 'coproducer', 'client']


class ProjectMember(models.Model):
    """Project team members with roles"""
    ROLE_CHOICES = [
        ('coproducer', 'Co-Producer'),  # Can edit and push
        ('client', 'Client'),  # View only
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='members')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='project_memberships')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='members_added')
    
    class Meta:
        unique_together = [['project', 'user']]
        ordering = ['-added_at']
    
    def __str__(self):
        return f"{self.user.username} - {self.role} on {self.project}"


class Version(models.Model):
    """Version created by a specific user"""
    project = models.ForeignKey(Project, related_name='versions', on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='versions_created')
    commit_message = models.TextField(null=True, blank=True)
    file = models.FileField(upload_to=project_upload_path, null=True, blank=True)
    hash = models.CharField(max_length=64, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_count = models.IntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        creator = self.created_by.username if self.created_by else 'Unknown'
        return f"{self.project} - v{self.id} by {creator}"
    
    def save(self, *args, **kwargs):
        if self.commit_message:
            self.commit_message = sanitize_text(self.commit_message)
        if self.hash:
            self.hash = sanitize_text(self.hash)
        super().save(*args, **kwargs)
    
    def get_version_number(self):
        versions = Version.objects.filter(
            project=self.project,
            created_at__lte=self.created_at
        ).order_by('created_at')
        return list(versions).index(self) + 1
    
    def get_file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0


class PendingPush(models.Model):
    """Push request with approval workflow"""
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('awaiting_approval', 'Awaiting Approval'),
        ('approved', 'Approved'),
        ('processing', 'Processing'),
        ('zipping', 'Zipping'),
        ('comparing', 'Comparing'),
        ('done', 'Done'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected')
    ]
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='pushes_created')
    commit_message = models.TextField()
    file_list = models.JSONField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    progress = models.IntegerField(default=0)
    message = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    # Approval workflow
    approved_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='pushes_approved')
    approved_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(null=True, blank=True)
    
    version = models.ForeignKey(Version, on_delete=models.SET_NULL, null=True, blank=True)
    error_details = models.TextField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Push {self.id} by {self.created_by.username} - {self.project} - {self.status}"
    
    def save(self, *args, **kwargs):
        if self.commit_message:
            self.commit_message = sanitize_text(self.commit_message)
        if self.message:
            self.message = sanitize_text(self.message)
        if self.error_details:
            self.error_details = sanitize_text(self.error_details)
        
        if self.file_list and isinstance(self.file_list, list):
            cleaned_list = []
            for file_entry in self.file_list:
                if isinstance(file_entry, dict):
                    cleaned_entry = {}
                    for key, value in file_entry.items():
                        if isinstance(value, str):
                            cleaned_entry[key] = sanitize_text(value)
                        else:
                            cleaned_entry[key] = value
                    cleaned_list.append(cleaned_entry)
                else:
                    cleaned_list.append(file_entry)
            self.file_list = cleaned_list
        
        super().save(*args, **kwargs)
    
    def is_active(self):
        return self.status in ['pending', 'awaiting_approval', 'approved', 'processing', 'zipping', 'comparing']
    
    def mark_completed(self):
        from django.utils import timezone
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message=None):
        from django.utils import timezone
        self.status = 'failed'
        self.progress = 100
        self.completed_at = timezone.now()
        if error_message:
            self.error_details = sanitize_text(error_message)
        self.save()
    
    def approve(self, approver):
        """Approve a push and start processing"""
        from django.utils import timezone
        self.status = 'approved'
        self.approved_by = approver
        self.approved_at = timezone.now()
        self.save()
    
    def reject(self, rejector, reason=None):
        """Reject a push"""
        from django.utils import timezone
        self.status = 'rejected'
        self.approved_by = rejector
        self.approved_at = timezone.now()
        self.rejection_reason = sanitize_text(reason) if reason else None
        self.completed_at = timezone.now()
        self.save()


class ActivityLog(models.Model):
    """Track all project activities"""
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
    
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='activity_logs')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activities')
    action = models.CharField(max_length=30, choices=ACTION_CHOICES)
    description = models.TextField()
    metadata = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.project} - {self.action} by {self.user.username if self.user else 'System'}"
    
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


class SampleBasket(models.Model):
    """Sample files uploaded to project"""
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='samples')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='samples_uploaded')
    name = models.CharField(max_length=255)
    file = models.FileField(upload_to=sample_upload_path)
    file_size = models.BigIntegerField(null=True, blank=True)
    file_type = models.CharField(max_length=50, null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    tags = models.JSONField(default=list, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-uploaded_at']
    
    def __str__(self):
        return f"{self.name} - {self.project}"
    
    def save(self, *args, **kwargs):
        if self.name:
            self.name = sanitize_text(self.name)
        if self.description:
            self.description = sanitize_text(self.description)
        
        if not self.file_size and self.file:
            try:
                self.file_size = self.file.size
            except:
                pass
        
        super().save(*args, **kwargs)
    
    def get_file_size_mb(self):
        if self.file_size:
            return round(self.file_size / (1024 * 1024), 2)
        return 0