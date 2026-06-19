import uuid as uuid_lib

from django.db import models


class BroadcastStatus(models.TextChoices):
    """Canonical statuses for a WhatsApp broadcast message lifecycle.

    Values are lowercase to match the payloads emitted by the Flows API
    (on dispatch) and by the courier on the msgs.topic exchange (during
    the lifecycle). The enum mirrors the upstream domain so dashboards
    and metrics can reason about the real state without lossy mappings.

    Lifecycle (typical happy path):
        INITIALIZING → PENDING → QUEUED → SENT → WIRED → DELIVERED → READ

    Failure states are terminal and exclusive:
        ERRORED  → Transient failure; the courier will retry automatically.
        FAILED   → Permanent failure; no further attempts will be made.
                   error_message holds the reason for both states.

    States in detail:
        INITIALIZING → Flows internal pre-queue state (rare).
        PENDING      → Courier accepted the request, not queued yet.
        QUEUED       → In broker, waiting to be sent to the provider.
        SENT         → Handed off to Meta.
        WIRED        → Meta acknowledged receipt.
        DELIVERED    → Reached the recipient's device.
        READ         → Opened by the recipient.
        ERRORED      → Transient error (will retry).
        FAILED       → Permanent failure (no retries).
        UNKNOWN      → Unmapped upstream value; payload preserved in
                       last_payload for analysis.
    """

    INITIALIZING = "initializing", "Initializing"
    PENDING = "pending", "Pending"
    QUEUED = "queued", "Queued"
    SENT = "sent", "Sent"
    WIRED = "wired", "Wired"
    DELIVERED = "delivered", "Delivered"
    READ = "read", "Read"
    ERRORED = "errored", "Errored"
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

    Conversion attribution:
        ``order_form_id`` and ``order_id`` capture the commercial origin
        of the broadcast so a later VTEX ``invoiced`` event can be
        attributed back to it. The conversion itself is materialized in
        a dedicated ``BroadcastConversion`` row (one per (project,
        order_id)) so multiple broadcasts targeting the same purchase
        share a single conversion record without inflating metrics.

        - Abandoned cart flow: ``order_form_id`` is filled at dispatch
          (the cart exists but no order does).
        - Order-status / payment-recovery flows: ``order_id`` is filled
          at dispatch (the order already exists).

        Both columns stay nullable on this row; the canonical pairing
        of ``order_form_id`` and ``order_id`` lives on
        ``BroadcastConversion`` once the purchase is confirmed.
    """

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True)

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
        default=BroadcastStatus.QUEUED,
    )
    # The status before the last transition; empty string on the initial row.
    previous_status = models.CharField(max_length=32, blank=True, default="")
    status_updated_at = models.DateTimeField(null=True, blank=True)

    # Populated when status=FAILED; holds a short human-readable reason
    # (e.g. exception class + message) so we can scan failures without
    # parsing last_payload, which keeps the full raw error.
    error_message = models.TextField(blank=True, default="")

    last_payload = models.JSONField(default=dict, blank=True)

    order_form_id = models.CharField(max_length=255, null=True, blank=True)
    order_id = models.CharField(max_length=255, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["broadcast_id"]),
            models.Index(fields=["external_message_id"]),
            models.Index(fields=["project", "created_at"]),
            models.Index(fields=["integrated_agent", "created_at"]),
            models.Index(fields=["project", "status"]),
            models.Index(fields=["project", "order_form_id"]),
            models.Index(fields=["project", "order_id"]),
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


class BroadcastConversion(models.Model):
    """Represents a finalized purchase attributed to a broadcast dispatch.

    A single row materializes the moment a VTEX order transitions to
    ``invoiced``. The unique constraint on ``(project, order_id)``
    enforces a 1:1 mapping with the purchase event — multiple
    BroadcastMessage rows targeting the same order (e.g. abandoned
    cart followed by payment recovery) collapse here into a single
    conversion, avoiding double-counting in analytics.

    ``integrated_agent`` is filled with the last-touch broadcast's
    agent at creation time so per-agent conversion reports can be
    answered by a simple ``GROUP BY integrated_agent_id``. It is
    nullable because the matched broadcast may have lost its agent
    (``SET_NULL`` on agent deletion) by the time the invoice arrives,
    and may also remain unset for projects that disabled tracking.

    ``broadcast`` snapshots the exact ``BroadcastMessage`` credited as
    the attribution source at conversion time (last-touch rule applied
    at write). This is the durable source of truth for "which dispatch
    drove this sale" — the rule that picks the broadcast may evolve,
    but rows already written keep pointing at the broadcast that was
    attributed at the moment. Nullable for legacy rows (created before
    this column existed) and so that ``BroadcastMessage`` deletion via
    ``SET_NULL`` does not cascade to the conversion.

    The row is write-once: subsequent ``invoiced`` re-deliveries hit
    the unique constraint and are ignored at the use-case level
    (logged as ``conversion_already_recorded``).
    """

    uuid = models.UUIDField(default=uuid_lib.uuid4, editable=False, unique=True)

    project = models.ForeignKey(
        "projects.Project",
        on_delete=models.CASCADE,
        related_name="broadcast_conversions",
    )
    integrated_agent = models.ForeignKey(
        "agents.IntegratedAgent",
        on_delete=models.SET_NULL,
        related_name="broadcast_conversions",
        null=True,
        blank=True,
    )
    broadcast = models.ForeignKey(
        "BroadcastMessage",
        on_delete=models.SET_NULL,
        related_name="conversions",
        null=True,
        blank=True,
    )

    order_id = models.CharField(max_length=255)
    order_form_id = models.CharField(max_length=255, null=True, blank=True)

    value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=8, blank=True, default="")

    converted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["project", "converted_at"]),
            models.Index(fields=["integrated_agent", "converted_at"]),
            models.Index(fields=["project", "order_form_id"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["project", "order_id"],
                name="broadcast_conversions_project_order_unique",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"BroadcastConversion(uuid={self.uuid}, "
            f"order_id={self.order_id}, project_id={self.project_id})"
        )
