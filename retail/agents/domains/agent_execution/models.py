from uuid import uuid4

from django.db import models

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.templates.models import Template


class AgentExecutionStatus(models.TextChoices):
    """Status choices for agent execution."""

    PROCESSING = "processing", "Processing"
    SUCCESS = "success", "Success"
    ERROR = "error", "Error"
    SKIP = "skip", "Skip"


class AgentExecution(models.Model):
    """
    Model to track agent execution logs.

    Stores execution data including webhook payloads, lambda requests/responses,
    and broadcast results for debugging and monitoring purposes.

    Traces are stored in S3 as JSON files containing an array of trace objects.
    The traces_s3_key field stores the S3 key to the traces file.
    """

    uuid = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    contact_urn = models.CharField(max_length=255, db_index=True)
    status = models.CharField(
        max_length=20,
        choices=AgentExecutionStatus.choices,
        default=AgentExecutionStatus.PROCESSING,
    )
    integrated_agent = models.ForeignKey(
        IntegratedAgent,
        on_delete=models.SET_NULL,
        null=True,
        related_name="executions",
    )
    created_on = models.DateTimeField(auto_now_add=True)
    updated_on = models.DateTimeField(auto_now=True)
    template = models.ForeignKey(
        Template,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executions",
    )
    broadcast_id = models.BigIntegerField(null=True, blank=True, db_index=True)

    # Forward link to the BroadcastMessage row created at dispatch time
    # (see retail.broadcasts). Lets the agent-logs API surface the
    # courier-driven lifecycle (delivered / read / failed) through a
    # single select_related JOIN.
    #
    # ``to_field="uuid"`` is required: BroadcastMessage's PK is a
    # ``BIGSERIAL`` ``id`` (see broadcasts.0003), so without this the
    # FK column would be ``bigint`` and the buffer's UUID writes would
    # overflow with ``bigint out of range``.
    broadcast_message = models.ForeignKey(
        "broadcasts.BroadcastMessage",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="executions",
        to_field="uuid",
    )

    # Fields for official agents (order status, abandoned cart)
    order_id = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    # ISO-4217 three-letter code (BRL, USD, ...). Sourced from VTEX
    # store preferences at execution time. Null on legacy rows; the
    # API layer falls back to ``BRL`` when reading.
    currency = models.CharField(max_length=3, null=True, blank=True)

    # S3 key to the traces JSON file
    # File contains array of trace objects with structure:
    # {"type": "webhook_received|lambda_request|lambda_response|broadcast_response|error|skip",
    #  "timestamp": "ISO datetime", "data": {...}}
    traces_s3_key = models.CharField(max_length=500, null=True, blank=True)

    error_message = models.TextField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(
                fields=["integrated_agent", "created_on"],
                name="agent_exec_agent_created_idx",
            ),
            models.Index(
                fields=["status", "created_on"],
                name="agent_exec_status_created_idx",
            ),
            models.Index(
                fields=["contact_urn", "integrated_agent", "created_on"],
                name="agent_exec_contact_agent_idx",
            ),
        ]
        ordering = ["-created_on"]

    def __str__(self):
        return f"Execution {self.uuid} - {self.status} - {self.contact_urn}"
