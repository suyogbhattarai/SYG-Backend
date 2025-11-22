# projects/models.py
"""
Project models with UUID support and proper security
"""

import uuid
from django.db import models
from django.contrib.auth.models import User


def sanitize_text(text):
    """Remove null characters"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


class Project(models.Model):
    """Project with UUID for secure access"""
    uid = models.CharField(max_length=16, unique=True, db_index=True, editable=False)
    
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_projects_new'
    )
    name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    description = models.TextField(null=True, blank=True)
    
    require_push_approval = models.BooleanField(default=False)
    ignore_patterns = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ['-updated_at']
        unique_together = [['owner', 'name']]
        verbose_name = 'Project (New)'
        verbose_name_plural = 'Projects (New)'
        db_table = 'projects_project'
        indexes = [
            models.Index(fields=['uid']),
            models.Index(fields=['owner', '-updated_at']),
        ]

    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid.uuid4().hex[:16]
        if self.description:
            self.description = sanitize_text(self.description)
        if self.name:
            self.name = sanitize_text(self.name)
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.owner.username}/{self.name} (UID:{self.uid[:8]})"
    
    def get_version_count(self):
        """Get total completed versions"""
        return self.versions_new.filter(status='completed').count()
    
    def get_latest_version(self):
        """Get most recent completed version"""
        return self.versions_new.filter(status='completed').order_by('-created_at').first()
    
    def has_active_push(self):
        """Check for active pushes"""
        return self.pushes_new.filter(
            status__in=['pending', 'processing', 'awaiting_approval']
        ).exists()
    
    def get_user_role(self, user):
        """Get user role in project"""
        if user == self.owner:
            return 'owner'
        
        member = self.members_new.filter(user=user).first()
        if member:
            return member.role
        return None
    
    def user_can_edit(self, user):
        """Check edit permission"""
        role = self.get_user_role(user)
        return role in ['owner', 'coproducer']
    
    def user_can_view(self, user):
        """Check view permission"""
        role = self.get_user_role(user)
        return role in ['owner', 'coproducer', 'client']


class ProjectMember(models.Model):
    """Project member with roles"""
    ROLE_CHOICES = [
        ('coproducer', 'Co-Producer'),
        ('client', 'Client'),
    ]
    
    project = models.ForeignKey(
        Project,
        on_delete=models.CASCADE,
        related_name='members_new'
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='project_memberships_new'
    )
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    added_at = models.DateTimeField(auto_now_add=True)
    added_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name='members_added_new'
    )
    
    class Meta:
        unique_together = [['project', 'user']]
        ordering = ['-added_at']
        verbose_name = 'Project Member (New)'
        verbose_name_plural = 'Project Members (New)'
        db_table = 'projects_projectmember'
    
    def __str__(self):
        return f"{self.user.username} - {self.role} on {self.project}"