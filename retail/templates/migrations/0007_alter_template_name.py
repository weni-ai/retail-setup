# Generated by Django 5.1.1 on 2025-05-23 15:07

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("templates", "0006_merge_20250522_1220"),
    ]

    operations = [
        migrations.AlterField(
            model_name="template",
            name="name",
            field=models.CharField(),
        ),
    ]
