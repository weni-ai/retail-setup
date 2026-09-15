import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0015_projectonboarding_is_active_and_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="is_live_desk_copilot",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="project",
            name="parent_project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="copilot_projects",
                to="projects.project",
            ),
        ),
        migrations.AddConstraint(
            model_name="project",
            constraint=models.CheckConstraint(
                check=(
                    models.Q(
                        ("is_live_desk_copilot", False),
                        ("parent_project__isnull", True),
                    )
                    | models.Q(
                        ("is_live_desk_copilot", True),
                        ("parent_project__isnull", False),
                    )
                ),
                name="projects_project_copilot_requires_parent",
            ),
        ),
    ]
