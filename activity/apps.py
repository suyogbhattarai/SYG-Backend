# activity/apps.py
"""
App configuration for activity
"""

from django.apps import AppConfig


class ActivityConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'activity'
    verbose_name = 'Activity Logs'
    
    def ready(self):
        """Import signals when app is ready"""
        import activity.signals