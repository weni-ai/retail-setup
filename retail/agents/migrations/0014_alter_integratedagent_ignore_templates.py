# Generated by Django 5.1.1 on 2025-05-23 21:12

import django.contrib.postgres.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0013_merge_20250523_1759"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integratedagent",
            name="ignore_templates",
            field=django.contrib.postgres.fields.ArrayField(
                base_field=models.CharField(), blank=True, default=list, size=None
            ),
        ),
    ]
