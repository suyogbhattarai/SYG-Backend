# projects/permissions.py
"""
Custom permissions for projects app
"""

from rest_framework import permissions


class IsProjectOwner(permissions.BasePermission):
    """
    Permission check: User must be the project owner
    """
    def has_object_permission(self, request, view, obj):
        # obj can be Project or related model
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'project'):
            return obj.project.owner == request.user
        return False


class CanViewProject(permissions.BasePermission):
    """
    Permission check: User must have view access (owner, coproducer, or client)
    """
    def has_object_permission(self, request, view, obj):
        # Get project from object
        if hasattr(obj, 'user_can_view'):
            project = obj
        elif hasattr(obj, 'project'):
            project = obj.project
        else:
            return False
        
        return project.user_can_view(request.user)


class CanEditProject(permissions.BasePermission):
    """
    Permission check: User must have edit access (owner or coproducer)
    """
    def has_object_permission(self, request, view, obj):
        # Get project from object
        if hasattr(obj, 'user_can_edit'):
            project = obj
        elif hasattr(obj, 'project'):
            project = obj.project
        else:
            return False
        
        return project.user_can_edit(request.user)


class IsOwnerOrReadOnly(permissions.BasePermission):
    """
    Permission check: Read-only for members, full access for owner
    """
    def has_object_permission(self, request, view, obj):
        # Read permissions are allowed for any member
        if request.method in permissions.SAFE_METHODS:
            if hasattr(obj, 'user_can_view'):
                return obj.user_can_view(request.user)
            elif hasattr(obj, 'project'):
                return obj.project.user_can_view(request.user)
        
        # Write permissions only for owner
        if hasattr(obj, 'owner'):
            return obj.owner == request.user
        elif hasattr(obj, 'project'):
            return obj.project.owner == request.user
        
        return False