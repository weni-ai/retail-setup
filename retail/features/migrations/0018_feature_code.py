# Generated by Django 5.1.1 on 2025-02-05 14:57

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("features", "0017_alter_integratedfeature_feature_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="feature",
            name="code",
            field=models.CharField(blank=True, max_length=25, null=True),
        ),
    ]
