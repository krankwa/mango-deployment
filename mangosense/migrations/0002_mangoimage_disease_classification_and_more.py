# Generated by Django 5.2.4 on 2025-07-17 11:53

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('mangosense', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='mangoimage',
            name='disease_classification',
            field=models.CharField(blank=True, max_length=50),
        ),
        migrations.AddField(
            model_name='mangoimage',
            name='is_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='mangoimage',
            name='notes',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='mangoimage',
            name='verified_by',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='verified_images', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='mangoimage',
            name='verified_date',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
