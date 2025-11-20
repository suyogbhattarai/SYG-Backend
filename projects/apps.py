# projects/apps.py
"""
App configuration for projects
"""

from django.apps import AppConfig


class ProjectsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'projects'
    verbose_name = 'Project Management'
    
    def ready(self):
        """Import signals when app is ready"""
        import projects.signals