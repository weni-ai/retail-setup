import uuid

from django.db import models

from retail.projects.models import Project

class Feature(models.Model):

    create_on = models.DateField("when are created the new feature", auto_now_add=True)
    description = models.TextField(null=True)
    name = models.CharField(max_length=256)
    uuid = models.UUIDField("UUID", primary_key=True, default=uuid.uuid4, editable=False)
    category = models.CharField(max_length=256)

    def __str__(self):
        return f"Name: {self.name}"


class FeatureVersion(models.Model):
    created_at = models.DateField(auto_now_add=True)
    uuid = models.UUIDField("UUID", primary_key=True, default=uuid.uuid4, editable=False)
    definition = models.JSONField()
    parameters = models.JSONField(null=True, blank=True)
    version = models.CharField(max_length=10, default="1.0")
    feature = models.ForeignKey(Feature, models.CASCADE, related_name="feature_version", null=True, blank=True)
    
    def __str__(self) -> str:
        return f"{self.feature.name} - {self.version} - {self.uuid}"


class FeatureIntegration(models.Model):
    feature_version = models.ForeignKey(FeatureVersion, on_delete=models.CASCADE, related_name="feature_integration")


class IntegratedFeature(models.Model):
    feature_version = models.ForeignKey(FeatureVersion, on_delete=models.CASCADE, related_name="integrated_feature")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="project")
    # add usuário e integrated_on (data que foi gerado o integrated_feature)

    def __str__(self) -> str:
        return self.feature_version.feature.name


class Flow(models.Model):
    uuid = models.UUIDField()
    flow_uuid = models.CharField(max_length=100, null=True)
    name = models.CharField(max_length=256)
    definition = models.JSONField()
    integrated_feature = models.ForeignKey(IntegratedFeature, on_delete=models.CASCADE, related_name="flows")
