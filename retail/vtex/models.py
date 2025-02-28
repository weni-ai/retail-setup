import uuid

from django.db import models
from retail.projects.models import Project
from retail.features.models import IntegratedFeature


class Cart(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("purchased", "Purchased"),
        ("delivered_success", "Delivered Success"),
        ("delivered_error", "Delivered Error"),
        ("empty", "Empty"),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    order_form_id = models.CharField(null=True, blank=True)
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now=True)
    status = models.CharField(
        max_length=20,
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
        IntegratedFeature, on_delete=models.CASCADE, related_name="carts_by_feature"
    )
    abandoned = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        status = "Abandoned" if self.abandoned else self.status.capitalize()
        return f"Cart: {self.phone_number}, Status: {status}, Last Modified: {self.modified_on:%Y-%m-%d %H:%M:%S}"

    class Meta:
        indexes = [models.Index(fields=["project", "status"])]
