from django.db import models
from django.contrib.postgres.fields import ArrayField

from uuid import uuid4


class IntegratedAgent(models.Model):
    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    channel_uuid = models.UUIDField(null=True)
    agent = models.ForeignKey(
        "Agent", on_delete=models.CASCADE, related_name="integrateds"
    )
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="integrated_agents"
    )
    is_active = models.BooleanField(default=True)
    ignore_templates = ArrayField(models.CharField(), blank=True, default=list)
    contact_percentage = models.PositiveIntegerField(default=10)
    config = models.JSONField(default=dict)
    global_rule_code = models.TextField(null=True)
    global_rule_prompt = models.TextField(null=True)

    # UUID of the parent agent for inheriting functionalities like order status notifications
    parent_agent_uuid = models.UUIDField(
        null=True,
        blank=True,
    )

    # Timestamp of when the agent was integrated into the project.
    created_on = models.DateTimeField(auto_now_add=True)
    # Running total of broadcasts delivered by this integrated agent.
    # Incremented atomically alongside ProjectBroadcastCounter on each
    # DELIVERED transition handled by the broadcast status consumer.
    broadcasts_delivered = models.PositiveBigIntegerField(default=0)

    def __str__(self):
        return f"{self.agent} - {self.project}"


class Credential(models.Model):
    key = models.CharField(max_length=255)
    label = models.CharField(max_length=255)
    value = models.CharField(max_length=8192)
    placeholder = models.CharField(max_length=255, null=True)
    is_confidential = models.BooleanField(default=False)

    integrated_agent = models.ForeignKey(
        "IntegratedAgent", on_delete=models.CASCADE, related_name="credentials"
    )

    class Meta:
        unique_together = ("key", "integrated_agent")

    def __str__(self) -> str:
        return f"{self.label} - {self.integrated_agent.agent.name}"
