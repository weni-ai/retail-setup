# Generated by Django 5.1.1 on 2025-06-02 15:23

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0006_project_config"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="project",
            index=models.Index(fields=["uuid"], name="projects_pr_uuid_75bd24_idx"),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(
                fields=["vtex_account"], name="projects_pr_vtex_ac_07ef3c_idx"
            ),
        ),
    ]
