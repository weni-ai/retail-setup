from uuid import uuid4

from django.db import models


class Agent(models.Model):
    """
    Credentials format:
    {
        "EXAMPLE_CREDENTIAL": {
          "label": "Label Example",
          "placeholder": "placeholder-example",
          "is_confidential": true
        },
    }
    """

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


class PreApprovedTemplate(models.Model):
    """
    The field is_valid controls if the pre approved template from meta is a valid
    template.

    is_valid = None if do not have response from meta;
    is_valid = False if response from meta if negative;
    is_valid = True if response from meta if positive.
    """

    agent = models.ForeignKey(
        "Agent", on_delete=models.CASCADE, null=True, related_name="templates"
    )
    slug = models.CharField(null=True)
    uuid = models.UUIDField(blank=True, default=uuid4)
    name = models.CharField()
    display_name = models.CharField()
    content = models.TextField(blank=True, null=True)
    is_valid = models.BooleanField(blank=True, null=True)
    start_condition = models.TextField()
    metadata = models.JSONField(null=True)
