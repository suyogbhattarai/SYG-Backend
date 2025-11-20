import os
import django
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "Dawlogs_backend.settings")
django.setup()

from versioning.models import PendingPush

for push in PendingPush.objects.all():
    if isinstance(push.file_list, str):
        try:
            push.file_list = json.loads(push.file_list)
            push.save(update_fields=['file_list'])
            print(f"Fixed push {push.id}")
        except Exception:
            print(f"Failed to fix push {push.id}")
