# Generated by Django 4.2.11 on 2024-04-13 21:35

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('app_instalaciones', '0001_initial'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='cuadroinst',
            name='created_at',
        ),
        migrations.RemoveField(
            model_name='cuadroinst',
            name='update_at',
        ),
    ]
