"""DRF serializers for the agent-logs API.

Three concerns live here:

- ``ListAgentLogsQuerySerializer`` parses the GET query string into a
  filter DTO. It accepts comma-separated lists for ``template_uuids``
  and ``statuses`` because that's how the API expects clients to
  encode multi-value filters in the URL.
- ``ExportAgentLogsBodySerializer`` parses the POST body. Same
  semantics, just JSON arrays instead of comma-joined strings.
- ``AgentLogRowSerializer`` renders an ``AgentExecution`` row in the
  agent-logs response shape. Pure-mapping helpers live in
  ``row_mapper`` so the CSV export uses the same transformations.

The serializers do not enforce ``page`` / ``page_size`` upper bounds
beyond a sane minimum — the view layer applies the default
``page_size = 20`` while still letting the value flow through for
forward compatibility.
"""

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional
from uuid import UUID

from rest_framework import serializers

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.row_mapper import (
    format_contact,
    needs_json_url,
    resolve_amount_value,
    resolve_currency,
    resolve_log_status,
    resolve_summary,
    resolve_template_name,
    resolve_template_uuid,
)
from retail.agents.domains.agent_execution.status_mapping import (
    LOG_STATUSES,
)
from retail.interfaces.services.aws_s3 import S3ServiceInterface


JSON_URL_TTL_SECONDS = 60 * 15

# ``amount.value`` is rendered as a precision-preserving string with
# two decimals (e.g. ``"100.00"``). DRF's default JSON encoder would
# otherwise render a ``Decimal`` as a float and drop trailing zeros,
# so we quantize + stringify at the serializer boundary.
_AMOUNT_QUANTUM = Decimal("0.01")


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


class _CommaSeparatedUUIDsField(serializers.Field):
    """Accept either a comma-separated string (query) or a list (body)."""

    default_error_messages = {
        "invalid": "Each entry must be a valid UUID.",
    }

    def to_internal_value(self, data) -> List[UUID]:
        if data is None or data == "":
            return []
        if isinstance(data, str):
            entries = _split_csv(data)
        elif isinstance(data, (list, tuple)):
            entries = [str(entry).strip() for entry in data if str(entry).strip()]
        else:
            self.fail("invalid")
            return []

        try:
            return [UUID(entry) for entry in entries]
        except (TypeError, ValueError):
            self.fail("invalid")
            return []

    def to_representation(self, value):
        return [str(v) for v in (value or [])]


class _CommaSeparatedStatusesField(serializers.Field):
    """Accept either a comma-separated string or a list of log-status values."""

    default_error_messages = {
        "invalid_status": "Unknown status value: {value}",
    }

    def to_internal_value(self, data) -> List[str]:
        if data is None or data == "":
            return []
        if isinstance(data, str):
            entries = _split_csv(data)
        elif isinstance(data, (list, tuple)):
            entries = [str(entry).strip() for entry in data if str(entry).strip()]
        else:
            self.fail("invalid_status", value=data)
            return []

        for entry in entries:
            if entry not in LOG_STATUSES:
                self.fail("invalid_status", value=entry)
        return entries

    def to_representation(self, value):
        return list(value or [])


class _BaseAgentLogsFilterSerializer(serializers.Serializer):
    search = serializers.CharField(
        required=False, allow_blank=True, allow_null=True, trim_whitespace=True
    )
    date = serializers.DateField(required=False, allow_null=True)
    template_uuids = _CommaSeparatedUUIDsField(required=False)
    statuses = _CommaSeparatedStatusesField(required=False)


class ListAgentLogsQuerySerializer(_BaseAgentLogsFilterSerializer):
    """Parse the GET query string into a list-filter DTO."""

    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, default=20)


class ExportAgentLogsBodySerializer(_BaseAgentLogsFilterSerializer):
    """Parse the POST body for ``/logs/export/``."""


class AgentLogRowSerializer(serializers.Serializer):
    """Render an ``AgentExecution`` in the agent-logs row shape."""

    uuid = serializers.SerializerMethodField()
    template_uuid = serializers.SerializerMethodField()
    template_name = serializers.SerializerMethodField()
    sent_at = serializers.SerializerMethodField()
    contact = serializers.SerializerMethodField()
    order_id = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()
    status = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    json_url = serializers.SerializerMethodField()

    def __init__(self, *args, **kwargs):
        self.s3_service: Optional[S3ServiceInterface] = kwargs.pop("s3_service", None)
        super().__init__(*args, **kwargs)

    def get_uuid(self, obj: AgentExecution) -> str:
        return str(obj.uuid)

    def get_template_uuid(self, obj: AgentExecution) -> Optional[str]:
        return resolve_template_uuid(obj)

    def get_template_name(self, obj: AgentExecution) -> Optional[str]:
        return resolve_template_name(obj)

    def get_sent_at(self, obj: AgentExecution) -> Optional[str]:
        if obj.created_on is None:
            return None
        return obj.created_on.isoformat()

    def get_contact(self, obj: AgentExecution) -> str:
        return format_contact(obj.contact_urn)

    def get_order_id(self, obj: AgentExecution) -> Optional[str]:
        return obj.order_id

    def get_amount(self, obj: AgentExecution) -> dict:
        value = resolve_amount_value(obj).quantize(
            _AMOUNT_QUANTUM, rounding=ROUND_HALF_UP
        )
        return {
            "value": str(value),
            "currency": resolve_currency(obj),
        }

    def get_status(self, obj: AgentExecution) -> str:
        return resolve_log_status(obj)

    def get_summary(self, obj: AgentExecution) -> str:
        return resolve_summary(resolve_log_status(obj))

    def get_json_url(self, obj: AgentExecution) -> Optional[str]:
        log_status = resolve_log_status(obj)
        if not needs_json_url(log_status):
            return None
        if not obj.traces_s3_key or self.s3_service is None:
            return None
        try:
            return self.s3_service.generate_presigned_url(
                obj.traces_s3_key, expiration=JSON_URL_TTL_SECONDS
            )
        except Exception:
            return None
