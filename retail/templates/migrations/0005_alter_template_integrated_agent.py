# Generated by Django 5.1.1 on 2025-05-21 13:21

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("agents", "0005_remove_integratedagent_lambda_arn"),
        ("templates", "0004_alter_template_integrated_agent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="template",
            name="integrated_agent",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="templates",
                to="agents.integratedagent",
            ),
        ),
    ]
