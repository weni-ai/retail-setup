# Generated by Django 5.1.1 on 2024-11-29 20:44

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("features", "0015_feature_can_vtex_integrate_feature_config_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="integratedfeature",
            name="config",
            field=models.JSONField(default=dict),
        ),
    ]