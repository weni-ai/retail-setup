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


class AgentRule(models.Model):
    """
    Represents a rule/template definition from an Agent's YAML configuration.

    Each AgentRule defines how a Template should be created when the agent
    is assigned to a project. The source_type determines the creation flow:
    - LIBRARY: Pre-approved template from Meta's library
    - USER_EXISTING: Template the user already has approved in Meta
    - CUSTOM: Template created by the system (e.g., abandoned cart)
    """

    SOURCE_TYPE_CHOICES = (
        ("LIBRARY", "Library Template - Pre-approved by Meta"),
        ("USER_EXISTING", "User Existing - Template user already has"),
        ("CUSTOM", "Custom - Created by system/user"),
    )

    agent = models.ForeignKey(
        "agents.Agent", on_delete=models.CASCADE, null=True, related_name="templates"
    )
    slug = models.CharField(null=True)
    uuid = models.UUIDField(blank=True, default=uuid4)
    name = models.CharField()
    display_name = models.CharField()
    content = models.TextField(blank=True, null=True)
    source_type = models.CharField(
        max_length=20,
        choices=SOURCE_TYPE_CHOICES,
        default="LIBRARY",
    )
    start_condition = models.TextField()
    metadata = models.JSONField(null=True)
    config = models.JSONField(default=dict)

    class Meta:
        db_table = "agents_preapprovedtemplate"

    def __str__(self):
        return f"{self.display_name}/{self.slug}"


# Backward-compatible alias (will be removed in a future cleanup)
PreApprovedTemplate = AgentRule
