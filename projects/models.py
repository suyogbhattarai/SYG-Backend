# projects/models.py
"""
Project and team management models
Handles projects, team members, and permissions
"""

from django.db import models
from django.contrib.auth.models import User


def sanitize_text(text):
    """Remove null characters and other problematic characters from text"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


class Project(models.Model):
    """
    Project owned by a user with collaboration support
    This is a NEW model that will eventually replace versioning.Project
    """
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='owned_projects_new'  # Different related_name to avoid conflict
    )
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
        unique_together = [['owner', 'name']]
        verbose_name = 'Project (New)'
        verbose_name_plural = 'Projects (New)'
        db_table = 'projects_project'

    def __str__(self):
        return f"{self.owner.username}/{self.name} (New)"
    
    def save(self, *args, **kwargs):
        if self.description:
            self.description = sanitize_text(self.description)
        if self.name:
            self.name = sanitize_text(self.name)
        super().save(*args, **kwargs)
    
    def get_version_count(self):
        """Get total number of versions"""
        return self.versions_new.count()
    
    def get_latest_version(self):
        """Get the most recent version"""
        return self.versions_new.order_by('-created_at').first()
    
    def has_active_push(self):
        """Check if there are any active pushes"""
        return self.pushes_new.filter(
            status__in=['pending', 'processing', 'zipping', 'comparing', 'awaiting_approval']
        ).exists()
    
    def get_user_role(self, user):
        """Get the role of a user in this project"""
        if user == self.owner:
            return 'owner'
        
        member = self.members_new.filter(user=user).first()
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
    """
    Project team members with roles
    This is a NEW model that will eventually replace versioning.ProjectMember
    """
    ROLE_CHOICES = [
        ('coproducer', 'Co-Producer'),  # Can edit and push
        ('client', 'Client'),  # View only
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