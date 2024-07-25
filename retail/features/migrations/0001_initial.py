# Generated by Django 5.0.7 on 2024-07-24 20:27

import django.db.models.deletion
import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Feature",
            fields=[
                (
                    "create_on",
                    models.DateField(
                        auto_now_add=True,
                        verbose_name="when are created the new feature",
                    ),
                ),
                ("description", models.TextField(null=True)),
                ("name", models.CharField(max_length=256)),
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        verbose_name="UUID",
                    ),
                ),
                ("category", models.CharField(max_length=256)),
            ],
        ),
        migrations.CreateModel(
            name="FeatureVersion",
            fields=[
                ("created_at", models.DateField(auto_now_add=True)),
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                        verbose_name="UUID",
                    ),
                ),
                ("definition", models.JSONField()),
                ("parameters", models.JSONField(blank=True, null=True)),
                ("version", models.CharField(default="1.0", max_length=10)),
                (
                    "feature",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_version",
                        to="features.feature",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="FeatureVersionTemplate",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4, primary_key=True, serialize=False
                    ),
                ),
                (
                    "feature_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="templates",
                        to="features.featureversion",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="feature_version_template",
                        to="projects.project",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="IntegratedFeatureVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "feature",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="integrated_feature",
                        to="features.feature",
                    ),
                ),
                (
                    "feature_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="integrated_feature",
                        to="features.featureversion",
                    ),
                ),
                (
                    "project",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="project",
                        to="projects.project",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="Flow",
            fields=[
                (
                    "uuid",
                    models.UUIDField(
                        default=uuid.uuid4, primary_key=True, serialize=False
                    ),
                ),
                ("flow_uuid", models.CharField(blank=True, max_length=100, null=True)),
                ("name", models.CharField(blank=True, max_length=256, null=True)),
                (
                    "integrated_feature_version",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="flows",
                        to="features.integratedfeatureversion",
                    ),
                ),
            ],
        ),
    ]
