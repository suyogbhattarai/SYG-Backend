import os
from celery import Celery
from celery.schedules import crontab
# set default Django settings module
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'Dawlogs_backend.settings')

# create Celery app
app = Celery('Dawlogs_backend')

# load config from Django settings (CELERY_*)
app.config_from_object('django.conf:settings', namespace='CELERY')

# auto-discover tasks.py in all installed apps
app.autodiscover_tasks()

app.conf.beat_schedule = {
    'cleanup-expired-downloads': {
        'task': 'versions.download_tasks.cleanup_expired_downloads',
        'schedule': crontab(hour=3, minute=0),  # Run daily at 3 AM
    },
}
