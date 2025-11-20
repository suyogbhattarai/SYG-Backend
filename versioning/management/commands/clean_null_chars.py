from django.core.management.base import BaseCommand
from versioning.models import Project, Version, PendingPush


def sanitize_text(text):
    """Remove null characters and other problematic characters"""
    if not text:
        return text
    return ''.join(char for char in text if ord(char) >= 32 or char in '\n\r\t')


def clean_dict(data):
    """Recursively clean dictionary data"""
    if isinstance(data, dict):
        return {k: clean_dict(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_dict(item) for item in data]
    elif isinstance(data, str):
        return sanitize_text(data)
    else:
        return data


class Command(BaseCommand):
    help = 'Clean null characters from database text fields'

    def handle(self, *args, **options):
        self.stdout.write('Starting database cleanup...')
        
        # Clean Projects
        project_count = 0
        for project in Project.objects.all():
            changed = False
            
            if project.name and '\x00' in project.name:
                project.name = sanitize_text(project.name)
                changed = True
            
            if project.description and '\x00' in project.description:
                project.description = sanitize_text(project.description)
                changed = True
            
            if changed:
                project.save()
                project_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Cleaned {project_count} projects'))
        
        # Clean Versions
        version_count = 0
        for version in Version.objects.all():
            changed = False
            
            if version.commit_message and '\x00' in version.commit_message:
                version.commit_message = sanitize_text(version.commit_message)
                changed = True
            
            if version.hash and '\x00' in version.hash:
                version.hash = sanitize_text(version.hash)
                changed = True
            
            if changed:
                version.save()
                version_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Cleaned {version_count} versions'))
        
        # Clean PendingPushes
        push_count = 0
        for push in PendingPush.objects.all():
            changed = False
            
            if push.commit_message and '\x00' in push.commit_message:
                push.commit_message = sanitize_text(push.commit_message)
                changed = True
            
            if push.message and '\x00' in push.message:
                push.message = sanitize_text(push.message)
                changed = True
            
            if push.error_details and '\x00' in push.error_details:
                push.error_details = sanitize_text(push.error_details)
                changed = True
            
            # Clean file_list JSON
            if push.file_list:
                original_json = str(push.file_list)
                if '\x00' in original_json:
                    push.file_list = clean_dict(push.file_list)
                    changed = True
            
            if changed:
                push.save()
                push_count += 1
        
        self.stdout.write(self.style.SUCCESS(f'Cleaned {push_count} pending pushes'))
        self.stdout.write(self.style.SUCCESS('Database cleanup complete!'))