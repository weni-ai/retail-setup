"""Use case: build a CSV export of agent logs and stash it on S3.

Filter semantics mirror ``ListAgentLogsUseCase`` exactly so the file
the user receives matches what they were viewing when they hit
"Export". Rows are streamed through a ``SpooledTemporaryFile`` (kept in
RAM up to ``EXPORT_SPOOL_MAX_BYTES``, then rolled over to disk) while
the queryset is consumed with ``.iterator()``; the spooled file is then
handed to ``upload_fileobj``, which lets boto3 switch to a multipart
upload for large exports. The full CSV is therefore never materialized
as a single in-memory blob.

The view layer treats the export as fire-and-forget (the API responds
``202 Accepted`` and the CSV is delivered out-of-band), so this use
case only returns the deterministic S3 key. Turning that key into the
emailed download link is a separate concern: the task signs it via
``BuildExportDownloadUrlUseCase`` and hands the result to
``SendAgentLogsExportEmailUseCase``.
"""

import csv
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone as dt_timezone
from typing import List, Optional, Sequence
from uuid import UUID

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db.models import Q
from django.utils import timezone

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.row_mapper import (
    format_amount_value,
    format_contact,
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

# CSV rows accumulate in memory up to this size before the spooled
# temp file rolls over to disk, keeping the working set bounded
# regardless of how many rows the filter matches.
EXPORT_SPOOL_MAX_BYTES = 5 * 1024 * 1024


class _Utf8CsvSink:
    """Adapt a binary stream to ``csv.writer``, which emits ``str``.

    ``csv.writer`` requires a text-mode file, but the export streams into
    a binary ``SpooledTemporaryFile`` (whose IO interface is incomplete
    before Python 3.11, so ``io.TextIOWrapper`` can't wrap it). This sink
    encodes each written row to UTF-8 and forwards it to the spool.
    """

    def __init__(self, stream):
        self._stream = stream

    def write(self, text: str) -> int:
        return self._stream.write(text.encode("utf-8"))


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
class ExportAgentLogsDTO:
    """Input DTO for ``ExportAgentLogsUseCase``.

    Same fields as the list filter, all optional from the API's
    perspective. The view passes ``agent_uuid`` / ``project_uuid`` from
    the URL + ``Project-Uuid`` header so the export can never escape
    the tenant boundary.
    """

    agent_uuid: UUID
    project_uuid: UUID
    search: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    template_uuids: Sequence[UUID] = field(default_factory=tuple)
    statuses: Sequence[str] = field(default_factory=tuple)
    user_email: Optional[str] = None

    @classmethod
    def from_task_args(
        cls,
        agent_uuid: str,
        project_uuid: str,
        search: Optional[str] = None,
        start_date_str: Optional[str] = None,
        end_date_str: Optional[str] = None,
        template_uuids: Optional[Sequence[str]] = None,
        statuses: Optional[Sequence[str]] = None,
        user_email: Optional[str] = None,
    ) -> "ExportAgentLogsDTO":
        """Build the filter from JSON-serializable Celery task arguments.

        Centralises the string→typed conversion so the task can stay
        glue: parses the ISO dates, validates the UUID strings, and
        normalises iterable defaults.
        """
        return cls(
            agent_uuid=UUID(agent_uuid),
            project_uuid=UUID(project_uuid),
            search=search,
            start_date=date.fromisoformat(start_date_str) if start_date_str else None,
            end_date=date.fromisoformat(end_date_str) if end_date_str else None,
            template_uuids=tuple(UUID(t) for t in (template_uuids or [])),
            statuses=tuple(statuses or ()),
            user_email=user_email,
        )


class ExportAgentLogsUseCase:
    """Materialise filtered agent logs to a CSV file in S3."""

    def __init__(self, s3_service: Optional[S3ServiceInterface] = None):
        if s3_service is not None:
            self.s3_service = s3_service
        else:
            self.s3_service = S3Service(bucket_name=_resolve_export_bucket())

    def execute(self, dto: ExportAgentLogsDTO) -> str:
        """Build the CSV, upload it to S3, and return the object key.

        The link delivered to the user is built separately (see
        ``BuildExportDownloadUrlUseCase``) so the download URL is minted
        fresh on click and never embeds a long-lived presigned URL.
        """
        queryset = self._build_queryset(dto)
        key = self._build_key(dto)

        row_count = 0
        with tempfile.SpooledTemporaryFile(
            max_size=EXPORT_SPOOL_MAX_BYTES, mode="w+b"
        ) as spool:
            writer = csv.writer(_Utf8CsvSink(spool))
            writer.writerow(CSV_HEADER)
            for execution in queryset.iterator():
                writer.writerow(self._row_for(execution))
                row_count += 1
            spool.seek(0)
            self.s3_service.upload_fileobj(spool, key, content_type="text/csv")

        logger.info(
            "Exported %d agent log rows for agent=%s project=%s key=%s",
            row_count,
            dto.agent_uuid,
            dto.project_uuid,
            key,
        )
        return key

    def _build_queryset(self, dto: ExportAgentLogsDTO):
        queryset = AgentExecution.objects.select_related(
            "template",
            "template__parent",
            "integrated_agent",
            "broadcast_message",
        ).filter(
            integrated_agent__uuid=dto.agent_uuid,
            integrated_agent__project__uuid=dto.project_uuid,
        )

        if dto.search:
            search = dto.search.strip()
            if search:
                queryset = queryset.filter(
                    Q(contact_urn__icontains=search) | Q(order_id__icontains=search)
                )

        if dto.start_date is not None and dto.end_date is not None:
            start_dt = datetime.combine(
                dto.start_date, time.min, tzinfo=dt_timezone.utc
            )
            end_dt = datetime.combine(dto.end_date, time.max, tzinfo=dt_timezone.utc)
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
            format_amount_value(execution),
            resolve_currency(execution),
            log_status,
            resolve_summary(log_status),
        ]

    @staticmethod
    def _build_key(dto: ExportAgentLogsDTO) -> str:
        ts = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        return f"exports/agent_logs/{dto.project_uuid}/{dto.agent_uuid}/{ts}.csv"
