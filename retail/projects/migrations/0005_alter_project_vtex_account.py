# Generated by Django 5.1.1 on 2025-01-11 00:43

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0004_project_vtex_account"),
    ]

    operations = [
        migrations.AlterField(
            model_name="project",
            name="vtex_account",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
    ]
