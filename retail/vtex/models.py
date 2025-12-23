from uuid import uuid4

from django.db import models
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project
from retail.features.models import IntegratedFeature


class Cart(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("purchased", "Purchased"),
        ("delivered_success", "Delivered Success"),
        ("delivered_error", "Delivered Error"),
        ("empty", "Empty"),
        ("skipped_identical_cart", "Skipped Identical Cart"),
        ("skipped_abandoned_cart_cooldown", "Skipped Abandoned Cart Cooldown"),
        ("skipped_below_minimum_value", "Skipped Below Minimum Value"),
    ]

    uuid = models.UUIDField(default=uuid4, editable=False, unique=True)
    order_form_id = models.CharField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=35,
        choices=STATUS_CHOICES,
        default="created",
        verbose_name="Status of Cart",
    )
    phone_number = models.CharField(max_length=15)
    config = models.JSONField(default=dict)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="carts_by_project"
    )
    integrated_feature = models.ForeignKey(
        IntegratedFeature,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="carts_by_feature",
    )
    integrated_agent = models.ForeignKey(
        IntegratedAgent,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="carts_by_agent",
    )
    abandoned = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    flows_channel_uuid = models.UUIDField(null=True, blank=True, editable=False)
    capi_notification_sent = models.BooleanField(default=False)

    def __str__(self):
        status = "Abandoned" if self.abandoned else self.status.capitalize()
        return f"Cart: {self.phone_number}, Status: {status}, Last Modified: {self.modified_on:%Y-%m-%d %H:%M:%S}"

    class Meta:
        indexes = [
            models.Index(fields=["project", "status"]),
            models.Index(fields=["order_form_id", "project"]),
            models.Index(fields=["abandoned"]),
            models.Index(fields=["phone_number"]),
            models.Index(fields=["phone_number", "status", "modified_on"]),
            models.Index(fields=["phone_number", "project", "modified_on"]),
        ]
