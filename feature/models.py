import uuid as uuid4

from django.db import models

from project.models import Project

class Feature(models.Model):
    create_on = models.DateField("when are created the new feature", auto_now_add=True)
    description = models.CharField(max_length=2560, null=True, blank=True)
    name = models.CharField(max_length=256, null=True, blank=True)
    uuid = models.UUIDField("UUID", primary_key=True, default=uuid4.uuid4, editable=False)

    def __str__(self):
        return f"Name: {self.name}\nDescription: {self.description}"

class FeatureVersion(models.Model):
    created_at = models.DateField(auto_now_add=True)
    uuid = models.UUIDField("UUID", primary_key=True, default=uuid4.uuid4, editable=False)
    definition = models.JSONField()
    parameters = models.JSONField(null=True, blank=True)
    version = models.CharField(max_length=10, default="1.0")
    feature = models.ForeignKey(Feature, models.CASCADE, related_name="feature_version", null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.feature.name} - {self.version} - {self.uuid}"


class IntegratedFeatureVersion(models.Model):
    feature_version = models.ForeignKey(FeatureVersion, on_delete=models.CASCADE, related_name="integrated_feature")
    feature = models.ForeignKey(Feature, on_delete=models.CASCADE, related_name="integrated_feature", null=True)
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, related_name="project", null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.feature.name} - {self.feature_version.version} - {self.project_uuid}"


class Flow(models.Model):
    uuid = models.UUIDField(default=uuid4.uuid4, primary_key=True)
    flow_uuid = models.CharField(max_length=100, null=True, blank=True)
    name = models.CharField(max_length=256, null=True, blank=True)
    integrated_feature_version = models.ForeignKey(IntegratedFeatureVersion, on_delete=models.CASCADE, related_name="flows")


class FeatureVersionTemplate(models.Model):
    uuid = models.UUIDField(default=uuid4.uuid4, primary_key=True)
    feature_version = models.ForeignKey(FeatureVersion, on_delete=models.CASCADE, related_name="templates")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="feature_version_template")
