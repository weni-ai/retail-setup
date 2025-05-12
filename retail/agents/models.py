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
    external_id = models.TextField()

    class Meta:
        unique_together = ("agent", "project")
