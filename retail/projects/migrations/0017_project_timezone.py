from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0016_project_live_desk_copilot"),
    ]

    operations = [
        migrations.AddField(
            model_name="project",
            name="timezone",
            field=models.CharField(blank=True, max_length=64, null=True),
        ),
    ]
