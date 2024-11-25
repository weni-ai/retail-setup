import uuid

from django.db import models
from retail.projects.models import Project


class Cart(models.Model):
    STATUS_CHOICES = [
        ("created", "Created"),
        ("purchased", "Purchased"),
        ("delivered_success", "Delivered Success"),
        ("delivered_error", "Delivered Error"),
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
    phone_number = models.CharField(max_length=15)
    config = models.JSONField(default=dict)
    project = models.ForeignKey(
        Project, on_delete=models.CASCADE, related_name="vtex_cart"
    )
    abandoned = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.phone_number} - {self.status} on {self.modified_on}"

    class Meta:
        indexes = [models.Index(fields=["project", "status"])]


class CartNotificationQueue(models.Model):
    """
    Queue for carts that need to be processed for abandoned notifications.
    """

    uuid = models.UUIDField(
        "UUID", primary_key=True, default=uuid.uuid4, editable=False
    )
    cart = models.OneToOneField(
        Cart, on_delete=models.CASCADE, related_name="notification_queue"
    )
    created_on = models.DateTimeField(auto_now_add=True)
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("processed", "Processed"),
            ("failed", "Failed"),
        ],
        default="pending",
        verbose_name="Notification Status",
    )
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Queue for cart {self.cart.uuid} - {self.status}"

    class Meta:
        indexes = [models.Index(fields=["status", "created_on"])]
