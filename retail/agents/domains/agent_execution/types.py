"""Typed enums for the agent_execution domain.

The trace ``type`` field used to be a free-form string scattered
across the buffer, the logger, and the docs. Centralising the values
here gives autocomplete + a single place to update when a new trace
type is introduced, and mirrors the pattern already established by
``AgentExecutionStatus`` in ``models.py``.
"""

from django.db import models


class ExecutionTraceType(models.TextChoices):
    """Discriminator for the per-trace ``type`` field on the JSON
    written to S3.

    The wire values match what shipped in earlier releases so already-
    written trace files keep parsing.
    """

    WEBHOOK_RECEIVED = "webhook_received", "Webhook received"
    LAMBDA_REQUEST = "lambda_request", "Lambda request"
    LAMBDA_RESPONSE = "lambda_response", "Lambda response"
    BROADCAST_RESPONSE = "broadcast_response", "Broadcast response"
    ERROR = "error", "Error"
    SKIP = "skip", "Skip"
