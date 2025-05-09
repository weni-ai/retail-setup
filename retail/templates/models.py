from django.db import models

from uuid import uuid4


class Template(models.Model):
    uuid = models.UUIDField(
        blank=True, editable=False, primary_key=True, default=uuid4()
    )
    name = models.CharField(unique=True)
    start_condition = models.TextField()
    current_version = models.OneToOneField(
        "Version",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="current_of",
    )


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
    template_name = models.CharField(unique=True, editable=False)
    integrations_app_uuid = models.UUIDField()
    project = models.ForeignKey(
        "projects.Project", on_delete=models.CASCADE, related_name="template_versions"
    )
    status = models.CharField(choices=STATUS_CHOICES, blank=True, default="PENDING")
    created_at = models.DateTimeField(auto_now_add=True)
    uuid = models.UUIDField(blank=True, editable=False, default=uuid4())
