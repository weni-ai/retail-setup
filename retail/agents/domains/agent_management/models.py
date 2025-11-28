from django.db import models

from uuid import uuid4


class Agent(models.Model):
    uuid = models.UUIDField(primary_key=True, blank=True, default=uuid4)
    name = models.CharField(max_length=255)
    slug = models.CharField()
    description = models.TextField()
    is_oficial = models.BooleanField(blank=True, default=False)
    lambda_arn = models.CharField(max_length=500, null=True, blank=True)
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="agents"
    )
    credentials = models.JSONField(null=True, default=dict)
    language = models.CharField(max_length=5, default="pt_BR")
    examples = models.JSONField(null=True, default=list)

    def __str__(self):
        return f"{self.name}/{self.slug}"


class PreApprovedTemplate(models.Model):
    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, null=True, related_name="templates"
    )
    slug = models.CharField(null=True)
    uuid = models.UUIDField(blank=True, default=uuid4)
    name = models.CharField()
    display_name = models.CharField()
    content = models.TextField(blank=True, null=True)
    is_valid = models.BooleanField(blank=True, null=True)
    start_condition = models.TextField()
    metadata = models.JSONField(null=True)
    config = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.display_name}/{self.slug}"
