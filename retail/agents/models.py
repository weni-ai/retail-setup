from django.db import models

from uuid import uuid4


class Agent(models.Model):
    uuid = models.UUIDField(primary_key=True, blank=True, default=uuid4)
    name = models.CharField(max_length=255)
    is_oficial = models.BooleanField(blank=True, default=False)
    lambda_arn = models.CharField(max_length=500, null=True, blank=True)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="agents"
    )
    templates = models.ManyToManyField("PreApprovedTemplate", related_name="agents")

    class Meta:
        unique_together = ("name", "project")


class IntegratedAgent(models.Model):
    uuid = models.UUIDField(primary_key=True, blank=True, default=uuid4)
    agent = models.ForeignKey(
        "Agent", on_delete=models.CASCADE, related_name="integrateds"
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="integrated_agents"
    )

    class Meta:
        unique_together = ("agent", "project")


class PreApprovedTemplate(models.Model):
    """
    The field is_valid controls if the pre approved template from meta is a valid
    template.

    is_valid = None if do not have response from meta;
    is_valid = False if response from meta if negative;
    is_valid = True if response from meta if positive.
    """

    name = models.CharField()
    content = models.TextField(blank=True, null=True)
    is_valid = models.BooleanField(blank=True, null=True)
    start_condition = models.TextField()
    metadata = models.JSONField(null=True)
