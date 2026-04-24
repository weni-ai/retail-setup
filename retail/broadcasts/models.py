import uuid as uuid_lib

from django.db import models


class BroadcastStatus(models.TextChoices):
    """Canonical statuses for a WhatsApp broadcast message lifecycle.

    Values are lowercase to match the payload emitted by the courier on
    the msgs.topic exchange (which mirrors Meta's WhatsApp Business API).

    Lifecycle:
        SENT       → Integrated agent called the WPP broadcast successfully;
                     message is on its way to Meta via the courier.
        DELIVERED  → Courier notified us that Meta confirmed delivery to
                     the recipient's device.
        READ       → Courier notified us that the recipient opened the message.
        FAILED     → Dispatch failed (e.g. Flows API error or future courier
                     failure notification). error_message holds the reason.
        UNKNOWN    → Unrecognized status received from the courier; the
                     full payload is preserved in last_payload for analysis
                     and the enum extended when the status is confirmed.
    """

    SENT = "sent", "Sent"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    FAILED = "failed", "Failed"
    UNKNOWN = "unknown", "Unknown"


class BroadcastMessage(models.Model):
    """Persistent log of every WhatsApp broadcast issued.

    Each row represents an outbound broadcast (PM term: "disparo"), not
    an inbound conversation. Conversations, which originate from
    user-initiated interactions, are tracked elsewhere and are subject
    to a separate blocking flow.

    Lifecycle:
        1. Row created at dispatch time with status=SENT (or FAILED, if
           the Flows call did not return a broadcast_id or raised), and
           with broadcast_id from the Flows API response.
        2. First courier EDA event links external_message_id (from Meta)
           to the row via broadcast_id.
        3. Subsequent courier events update status via external_message_id
           (broadcast_id is no longer present after the first event).
    """

    uuid = models.UUIDField(primary_key=True, default=uuid_lib.uuid4, editable=False)

    broadcast_id = models.BigIntegerField(null=True, blank=True)
    external_message_id = models.CharField(max_length=255, null=True, blank=True)

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="broadcast_messages",
    )
    integrated_agent = models.ForeignKey(
        "agents.IntegratedAgent",
        on_delete=models.SET_NULL,
        related_name="broadcast_messages",
        null=True,
        blank=True,
    )

    # Raw template name on our side (e.g. "abandoned_cart").
    template_name = models.CharField(max_length=255, blank=True, default="")
    # Full template name on Meta (e.g. "weni_abandoned_cart_1768996789226396").
    # Stored in Template.current_version.template_name on our side; also
    # echoed back by Flows in metadata.template.name.
    template_version = models.CharField(max_length=255, blank=True, default="")
    # Template UUID on the Flows side (from metadata.template.uuid in the
    # broadcast response). Distinct from our local Template.uuid.
    flows_template_uuid = models.UUIDField(null=True, blank=True)
    channel_uuid = models.UUIDField(null=True, blank=True)
    contact_urn = models.CharField(max_length=255, blank=True, default="")

    status = models.CharField(
        max_length=32,
        choices=BroadcastStatus.choices,
        default=BroadcastStatus.SENT,
    )
    # The status before the last transition; empty string on the initial row.
    previous_status = models.CharField(max_length=32, blank=True, default="")
    status_updated_at = models.DateTimeField(null=True, blank=True)

    # Populated when status=FAILED; holds a short human-readable reason
    # (e.g. exception class + message) so we can scan failures without
    # parsing last_payload, which keeps the full raw error.
    error_message = models.TextField(blank=True, default="")

    last_payload = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["broadcast_id"]),
            models.Index(fields=["external_message_id"]),
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["integrated_agent", "created_at"]),
            models.Index(fields=["project", "status"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["broadcast_id"],
                condition=models.Q(broadcast_id__isnull=False),
                name="broadcasts_broadcast_id_unique",
            ),
            models.UniqueConstraint(
                fields=["external_message_id"],
                condition=models.Q(external_message_id__isnull=False),
                name="broadcasts_external_message_id_unique",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"BroadcastMessage(uuid={self.uuid}, "
            f"broadcast_id={self.broadcast_id}, status={self.status})"
        )


class ProjectBroadcastCounter(models.Model):
    """Auxiliary counter holding the total delivered broadcasts per project.

    Each increment represents an outbound broadcast (PM term: "disparo")
    delivered to a contact on WhatsApp. This counter is NOT about inbound
    conversations (PM term: "conversa"): conversations are user-initiated
    interactions tracked in a separate flow with its own blocking rules.

    A single row per project allows O(1) checks of the blocking threshold
    without scanning BroadcastMessage. Incremented atomically using F
    expressions on each DELIVERED transition.
    """

    project = models.OneToOneField(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="broadcast_counter",
        primary_key=True,
    )
    total_delivered = models.PositiveBigIntegerField(default=0)
    blocked_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        if self.blocked_at is None:
            return (
                f"ProjectBroadcastCounter("
                f"project_uuid={self.project.uuid}, "
                f"total_delivered={self.total_delivered}, blocked=False)"
            )
        return (
            f"ProjectBroadcastCounter("
            f"project_uuid={self.project.uuid}, "
            f"total_delivered={self.total_delivered}, "
            f"blocked_at={self.blocked_at.isoformat()})"
        )
