"""
Migration to ensure hash field is properly configured with index
Run this migration: python manage.py makemigrations && python manage.py migrate
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('versions', '0001_initial'),  # Adjust to your last migration
    ]

    operations = [
        # Ensure hash field exists and is indexed
        migrations.AlterField(
            model_name='version',
            name='hash',
            field=models.CharField(max_length=64, null=True, blank=True, db_index=True),
        ),
        # Ensure file_size field exists
        migrations.AlterField(
            model_name='version',
            name='file_size',
            field=models.BigIntegerField(null=True, blank=True),
        ),
    ]