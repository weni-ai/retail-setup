from typing import Iterable
import uuid
import datetime

from django.db import models
from django.contrib.auth.models import User

from retail.projects.models import Project

class Feature(models.Model):

    categories = [
        ("ATIVO", "Ativo"),
        ("PASSIVO", "Passivo")
    ]

    created_on = models.DateTimeField("when are created the new feature", auto_now_add=True)
    description = models.TextField(null=True)
    name = models.CharField(max_length=256)
    uuid = models.UUIDField("UUID", primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=256, choices=categories, default="Ativo")

    def __str__(self):
        return self.name

    @property
    def last_version(self):
        return self.versions.order_by("created_on").last()


class IntelligentAgent(models.Model):

    personalities = [
        ("Amigável", "Amigável"),
        ("Cooperativo", "Cooperativo"),
        ("Extrovertido", "Extrovertido"),
        ("Generoso", "Generoso"),
        ("Relaxado", "Relaxado"),
        ("Organizado", "Organizado"),
        ("Sistemático", "Sistemático"),
        ("Inovador", "Inovador"),
        ("Criativo", "Criativo"),
        ("Intelectual", "Intelectual")
    ]

    uuid = models.UUIDField(default=uuid.uuid4)
    actions = models.JSONField(null=True)
    name = models.TextField()
    role = models.TextField()
    personality = models.TextField(choices=personalities, default="Amigável")
    instructions = models.JSONField(null=True)
    goal = models.TextField()

    def __str__(self) -> str:
        return f"{self.name} - {self.uuid}"


class FeatureVersion(models.Model):
    uuid = models.UUIDField("UUID", primary_key=True, default=uuid.uuid4, editable=False)

    definition = models.JSONField()
    parameters = models.JSONField(null=True, blank=True)
    version = models.CharField(max_length=10, default="1.0")
    feature = models.ForeignKey(Feature, models.CASCADE, related_name="versions", null=True, blank=True)
    IntelligentAgent = models.ForeignKey(IntelligentAgent, on_delete=models.CASCADE, related_name="versions", null=True)

    created_on = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return self.version


class IntegratedFeature(models.Model):
    uuid = models.UUIDField("UUID", primary_key=True, default=uuid.uuid4, editable=False)

    feature_version = models.ForeignKey(FeatureVersion, on_delete=models.CASCADE, related_name="integrated_features")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="integrated_features")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="integrated_features")
    parameters = models.JSONField(null=True, default=dict)

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="integrated_features")
    integrated_on = models.DateField(auto_now_add=True)

    def save(self, *args) -> None:
        self.feature = self.feature_version.feature
        return super().save(*args)

    def __str__(self) -> str:
        return self.feature_version.feature.name


class Flow(models.Model):
    uuid = models.UUIDField()
    flow_uuid = models.CharField(max_length=100, null=True)
    name = models.CharField(max_length=256)
    definition = models.JSONField()
    integrated_feature = models.ForeignKey(IntegratedFeature, on_delete=models.CASCADE, related_name="flows")
