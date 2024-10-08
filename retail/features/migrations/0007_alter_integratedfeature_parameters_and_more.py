# Generated by Django 5.1 on 2024-09-08 20:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("features", "0006_rename_dependencies_feature_functions_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="integratedfeature",
            name="parameters",
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
        migrations.AlterField(
            model_name="integratedfeature",
            name="sectors",
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
    ]
