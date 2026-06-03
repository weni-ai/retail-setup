"""Pure mappers from ``AgentExecution`` to the agent-logs row shape.

Shared between the JSON list serializer and the CSV export so they
agree on every transformation: status enum translation, contact
formatting, template-name resolution, summary derivation, and the
default currency for legacy rows. Keeping these as plain functions
also makes them trivial to unit-test without spinning up DRF or S3.
"""

import re
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.templates.models import Template
from retail.agents.domains.agent_execution.status_mapping import (
    LOG_STATUS_DELIVERED,
    LOG_STATUS_ERROR,
    LOG_STATUS_PROCESSING,
    LOG_STATUS_READ,
    LOG_STATUS_SENT,
    LOG_STATUS_SKIPPED,
    to_log_status,
)
from retail.broadcasts.models import BroadcastStatus


DEFAULT_CURRENCY = "BRL"

# ``amount.value`` is rendered as a precision-preserving string with two
# decimals (e.g. ``"100.00"``) so the JSON list response and the CSV
# export agree byte-for-byte and trailing zeros are never dropped.
AMOUNT_QUANTUM = Decimal("0.01")


STATUS_TO_SUMMARY: dict = {
    LOG_STATUS_PROCESSING: (
        "Automation is currently validating trigger rules and criteria."
    ),
    LOG_STATUS_SKIPPED: (
        "Delivery was skipped because the contact or order did not meet "
        "the trigger criteria."
    ),
    LOG_STATUS_ERROR: ("Technical failure during processing. Check JSON for details."),
    LOG_STATUS_SENT: "Message handed off to the messaging provider.",
    LOG_STATUS_DELIVERED: "Messaging provider confirmed delivery to the device.",
    LOG_STATUS_READ: "Contact has read the message.",
}


_BR_PHONE_RE = re.compile(r"^\+?(55)(\d{2})(\d{4,5})(\d{4})$")
_GENERIC_PHONE_RE = re.compile(r"^\+?(\d+)$")


def format_contact(contact_urn: Optional[str]) -> str:
    """Convert a stored contact URN into the display-ready string.

    Strips any ``whatsapp:`` (or other channel) prefix, then tries to
    apply the Brazilian phone grouping ``+55 11 91234-5678``. Falls
    back to the prefixed digits when the format is unknown — we never
    want to drop the value entirely.
    """
    if not contact_urn:
        return ""

    raw = contact_urn.strip()
    if ":" in raw:
        raw = raw.split(":", 1)[1]
    raw = raw.strip()

    digits_only = raw.lstrip("+")
    br_match = _BR_PHONE_RE.match(raw if raw.startswith("+") else f"+{digits_only}")
    if br_match:
        country, area, prefix, suffix = br_match.groups()
        return f"+{country} {area} {prefix}-{suffix}"

    generic_match = _GENERIC_PHONE_RE.match(raw)
    if generic_match:
        return f"+{generic_match.group(1)}" if not raw.startswith("+") else raw

    return raw


def template_display_name(template: Optional[Template]) -> Optional[str]:
    """Return a template's human-readable name, or ``None``.

    Custom templates expose ``display_name`` directly; templates
    inheriting from a ``PreApprovedTemplate`` use the parent's
    ``display_name``. Falls back to the raw ``Template.name`` when
    no display name is set.
    """
    if template is None:
        return None

    display_name = template.display_name
    if not display_name and template.parent is not None:
        display_name = template.parent.display_name

    return display_name or template.name


def resolve_template_name(execution: AgentExecution) -> Optional[str]:
    return template_display_name(execution.template)


def resolve_template_uuid(execution: AgentExecution) -> Optional[str]:
    if execution.template_id is None:
        return None
    return str(execution.template_id)


def resolve_amount_value(execution: AgentExecution) -> Decimal:
    """Return the raw decimal amount, defaulting to zero on legacy rows.

    The ``amount.value`` field on the API response is required (never
    null), so pre-currency rows that still have ``None`` for amount
    surface as ``0`` rather than a missing field.
    """
    return execution.amount if execution.amount is not None else Decimal("0")


def format_amount_value(execution: AgentExecution) -> str:
    """Return the amount quantized to two decimals as a string.

    Shared by the JSON list serializer and the CSV export so both render
    the value identically (e.g. ``"100.00"``) instead of one dropping
    trailing zeros (``"100"``) or a legacy ``None`` row diverging.
    """
    quantized = resolve_amount_value(execution).quantize(
        AMOUNT_QUANTUM, rounding=ROUND_HALF_UP
    )
    return str(quantized)


def resolve_currency(execution: AgentExecution) -> str:
    return execution.currency or DEFAULT_CURRENCY


def resolve_summary(log_status: str) -> str:
    return STATUS_TO_SUMMARY.get(log_status, "")


def resolve_has_json(execution: AgentExecution) -> bool:
    """Whether a stored JSON payload exists for this row.

    The buffer writes the traces file for every execution that reaches a
    terminal state, so any non-``processing`` row has a payload fetchable
    through the proxy endpoint. ``processing`` rows are still in flight
    and may have no object in S3 yet, so they report ``False``. Derived
    from the status alone — no S3 round-trip — to keep the list endpoint
    free of storage calls.
    """
    return resolve_log_status(execution) != LOG_STATUS_PROCESSING


def resolve_log_status(execution: AgentExecution) -> str:
    """Return the agent-logs status string for an ``AgentExecution`` row.

    Internal statuses other than ``success`` map 1:1 via
    ``status_mapping.to_log_status``. For ``success`` rows we consult
    the linked ``broadcasts.BroadcastMessage`` so the courier
    lifecycle bubbles up:

    - ``DELIVERED`` → ``delivered``
    - ``READ`` → ``read``
    - ``FAILED`` → ``error`` (permanent — even though dispatch succeeded)
    - everything else, or no link → ``sent``

    ``ERRORED`` (transient — courier will retry) intentionally stays in
    the ``sent`` bucket to avoid UI flapping when the retry succeeds.
    """
    if execution.status != AgentExecutionStatus.SUCCESS.value:
        return to_log_status(execution.status)

    broadcast_message = getattr(execution, "broadcast_message", None)
    if broadcast_message is None:
        return LOG_STATUS_SENT

    broadcast_status = broadcast_message.status
    if broadcast_status == BroadcastStatus.DELIVERED.value:
        return LOG_STATUS_DELIVERED
    if broadcast_status == BroadcastStatus.READ.value:
        return LOG_STATUS_READ
    if broadcast_status == BroadcastStatus.FAILED.value:
        return LOG_STATUS_ERROR
    return LOG_STATUS_SENT
