from django.db import models

from uuid import uuid4

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import PreApprovedTemplate


class Template(models.Model):
    uuid = models.UUIDField(blank=True, editable=False, primary_key=True, default=uuid4)
    name = models.CharField()
    parent = models.ForeignKey(
        PreApprovedTemplate, on_delete=models.PROTECT, null=True, blank=True
    )
    current_version = models.OneToOneField(
        "Version",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_of",
    )
    rule_code = models.TextField(null=True, blank=True)
    integrated_agent = models.ForeignKey(
        IntegratedAgent,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="templates",
    )
    metadata = models.JSONField(default=dict, blank=True)
    needs_button_edit = models.BooleanField(default=False)
    deleted_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    start_condition = models.TextField(null=True, blank=True)
    display_name = models.TextField(null=True, blank=True)
    variables = models.JSONField(default=list, blank=True)

    @property
    def is_custom(self) -> bool:
        return self.parent is None

    def __str__(self):
        return f"{self.display_name}/{self.name} [Version] {self.current_version}"


class Version(models.Model):
    STATUS_CHOICES = (
        ("APPROVED", "Approved"),
        ("IN_APPEAL", "In Appeal"),
        ("PENDING", "Pending"),
        ("REJECTED", "Rejected"),
        ("PENDING_DELETION", "Pending Deletion"),
        ("DELETED", "Deleted"),
        ("DISABLED", "Disabled"),
        ("LOCKED", "Locked"),
    )

    template = models.ForeignKey(
        "Template", on_delete=models.CASCADE, related_name="versions"
    )
    template_name = models.CharField()
    integrations_app_uuid = models.UUIDField()
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="template_versions"
    )
    status = models.CharField(choices=STATUS_CHOICES, blank=True, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(blank=True, editable=False, default=uuid4)

    def __str__(self):
        return f"{self.template_name} [Version] {self.uuid} [Status] {self.status}"
