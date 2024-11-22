import uuid

from django.db import models
from retail.projects.models import Project


class Cart(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("purchased", "Purchased"),
        ("abandoned", "Abandoned"),
        ("delivered success", "Delivered Success"),
        ("delivered error", "Delivered Error"),
        ("empty", "Empty"),
    ]
    uuid = models.UUIDField(
        "UUID", primary_key=True, default=uuid.uuid4, editable=False
    )
    created_on = models.DateTimeField(auto_now_add=True)
    modified_on = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="created",
        verbose_name="Status of Cart",
    )
    phone_number = models.CharField(max_length=256)
    config = models.JSONField(default=dict)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="vtex_cart"
    )

    def __str__(self):
        return f"{self.phone_number} - {self.status} on {self.modified_on}"
