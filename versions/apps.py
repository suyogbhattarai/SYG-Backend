# versions/apps.py
"""
App configuration for versions
"""

from django.apps import AppConfig


class VersionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'versions'
    verbose_name = 'Version Control'
    
    def ready(self):
        """Import signals when app is ready"""
        import versions.signals
        import versions.download_tasks