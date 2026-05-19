"""Use case: build a CSV export of agent logs and stash it on S3.

Filter semantics mirror ``ListAgentLogsUseCase`` exactly so the file
the user receives matches what they were viewing when they hit
"Export". The CSV is written in-memory with ``csv.writer`` (the
expected row counts are bounded by what an operator can usefully
review and the queryset is iterated with ``.iterator()`` to keep the
working set small) and uploaded as a single S3 PUT.

The view layer treats the export as fire-and-forget (the API responds
``202 Accepted`` and the CSV is delivered out-of-band), so this use
case returns the deterministic key + presigned URL for logging /
follow-up rather than driving any user-facing notification — delivery
channel is intentionally out of scope for this iteration.
"""

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone as dt_timezone
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.utils import timezone

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.row_mapper import (
    format_contact,
    resolve_amount_value,
    resolve_currency,
    resolve_log_status,
    resolve_summary,
    resolve_template_name,
    resolve_template_uuid,
)
from retail.agents.domains.agent_execution.status_mapping import (
    build_status_filter,
)
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service


logger = logging.getLogger(__name__)


CSV_HEADER = [
    "uuid",
    "template_uuid",
    "template_name",
    "sent_at",
    "contact",
    "order_id",
    "amount",
    "currency",
    "status",
    "summary",
]

PRESIGNED_URL_TTL_SECONDS = 60 * 60 * 24


def _resolve_export_bucket() -> str:
    """Return the configured export bucket or raise.

    Falls back from ``AGENT_LOGS_EXPORT_BUCKET`` to ``AWS_STORAGE_BUCKET_NAME``;
    a missing/empty value raises instead of silently routing exports to a
    placeholder bucket.
    """
    bucket = getattr(settings, "AGENT_LOGS_EXPORT_BUCKET", None) or getattr(
        settings, "AWS_STORAGE_BUCKET_NAME", None
    )
    if not bucket:
        raise ImproperlyConfigured(
            "AGENT_LOGS_EXPORT_BUCKET (or AWS_STORAGE_BUCKET_NAME) must be set "
            "to export agent logs."
        )
    return bucket


@dataclass(frozen=True)
class ExportAgentLogsFilter:
    """Filter input for ``ExportAgentLogsUseCase``.

    Same fields as the list filter, all optional from the API's
    perspective. The view passes ``agent_uuid`` / ``project_uuid`` from
    the URL + ``Project-Uuid`` header so the export can never escape
    the tenant boundary.
    """

    agent_uuid: UUID
    project_uuid: UUID
    search: Optional[str] = None
    date: Optional[date] = None
    template_uuids: Sequence[UUID] = field(default_factory=tuple)
    statuses: Sequence[str] = field(default_factory=tuple)

    @classmethod
    def from_task_args(
        cls,
        agent_uuid: str,
        project_uuid: str,
        search: Optional[str] = None,
        date_str: Optional[str] = None,
        template_uuids: Optional[Sequence[str]] = None,
        statuses: Optional[Sequence[str]] = None,
    ) -> "ExportAgentLogsFilter":
        """Build the filter from JSON-serializable Celery task arguments.

        Centralises the string→typed conversion so the task can stay
        glue: parses the ISO date, validates the UUID strings, and
        normalises iterable defaults.
        """
        parsed_date: Optional[date] = None
        if date_str:
            parsed_date = date.fromisoformat(date_str)

        return cls(
            agent_uuid=UUID(agent_uuid),
            project_uuid=UUID(project_uuid),
            search=search,
            date=parsed_date,
            template_uuids=tuple(UUID(t) for t in (template_uuids or [])),
            statuses=tuple(statuses or ()),
        )


class ExportAgentLogsUseCase:
    """Materialise filtered agent logs to a CSV file in S3."""

    def __init__(self, s3_service: Optional[S3ServiceInterface] = None):
        if s3_service is not None:
            self.s3_service = s3_service
        else:
            self.s3_service = S3Service(bucket_name=_resolve_export_bucket())

    def execute(self, dto: ExportAgentLogsFilter) -> Tuple[str, str]:
        """Build the CSV, upload it to S3, and return ``(key, presigned_url)``."""
        queryset = self._build_queryset(dto)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(CSV_HEADER)

        row_count = 0
        for execution in queryset.iterator():
            writer.writerow(self._row_for(execution))
            row_count += 1

        key = self._build_key(dto)
        content = buffer.getvalue().encode("utf-8")
        self.s3_service.put_object(key, content, content_type="text/csv")

        presigned_url = self.s3_service.generate_presigned_url(
            key, expiration=PRESIGNED_URL_TTL_SECONDS
        )

        logger.info(
            "Exported %d agent log rows for agent=%s project=%s key=%s",
            row_count,
            dto.agent_uuid,
            dto.project_uuid,
            key,
        )
        return key, presigned_url

    def _build_queryset(self, dto: ExportAgentLogsFilter):
        queryset = AgentExecution.objects.select_related(
            "template",
            "template__parent",
            "integrated_agent",
            "broadcast_message",
        ).filter(
            integrated_agent_id=dto.agent_uuid,
            integrated_agent__project__uuid=dto.project_uuid,
        )

        if dto.search:
            search = dto.search.strip()
            if search:
                queryset = queryset.filter(
                    Q(contact_urn__icontains=search) | Q(order_id__icontains=search)
                )

        if dto.date is not None:
            start_dt = datetime.combine(dto.date, time.min, tzinfo=dt_timezone.utc)
            end_dt = datetime.combine(dto.date, time.max, tzinfo=dt_timezone.utc)
            queryset = queryset.filter(created_on__range=(start_dt, end_dt))

        if dto.template_uuids:
            queryset = queryset.filter(template_id__in=list(dto.template_uuids))

        if dto.statuses:
            queryset = queryset.filter(build_status_filter(dto.statuses))

        return queryset.order_by("-created_on", "uuid")

    def _row_for(self, execution: AgentExecution) -> List[str]:
        log_status = resolve_log_status(execution)
        sent_at = (
            execution.created_on.isoformat() if execution.created_on is not None else ""
        )
        return [
            str(execution.uuid),
            resolve_template_uuid(execution) or "",
            resolve_template_name(execution) or "",
            sent_at,
            format_contact(execution.contact_urn),
            execution.order_id or "",
            str(resolve_amount_value(execution)),
            resolve_currency(execution),
            log_status,
            resolve_summary(log_status),
        ]

    @staticmethod
    def _build_key(dto: ExportAgentLogsFilter) -> str:
        ts = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        return f"exports/agent_logs/{dto.project_uuid}/{dto.agent_uuid}/{ts}.csv"
