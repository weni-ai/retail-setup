"""Use case: paginated agent-logs query for the public API.

Surface tailored to the agent-logs API: page/page_size + total instead of
limit/offset, ILIKE search across contact_urn / order_id, multi-status
and multi-template OR filters, and a date filter that is a single
calendar day rather than an arbitrary range.

The use case is also responsible for resolving the per-row presigned
``json_url`` so the view stays free of S3 wiring. The presigned URL
TTL is short (15 minutes) — long enough for an operator to download
the trace JSON after the response renders, short enough that a
leaked URL cannot be replayed indefinitely.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone as dt_timezone
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from django.db.models import Q

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.services.traces_storage import (
    resolve_traces_bucket,
)
from retail.agents.domains.agent_execution.status_mapping import (
    build_status_filter,
)
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.services.aws_s3.service import S3Service


logger = logging.getLogger(__name__)


JSON_URL_TTL_SECONDS = 60 * 15


@dataclass(frozen=True)
class ListAgentLogsDTO:
    """Input DTO for ``ListAgentLogsUseCase``.

    ``agent_uuid`` is the ``IntegratedAgent.uuid`` (same convention as
    the rest of ``/api/v3/agents/assigneds/{pk}/...``). ``project_uuid``
    scopes the query to a single tenant — the view passes the
    ``Project-Uuid`` header value down so this use case never returns
    rows from a different project.

    ``statuses`` carries log-status values (``skipped``, ``sent`` …);
    the use case translates them to internal values internally.
    """

    agent_uuid: UUID
    project_uuid: UUID
    search: Optional[str] = None
    date: Optional[date] = None
    template_uuids: Sequence[UUID] = field(default_factory=tuple)
    statuses: Sequence[str] = field(default_factory=tuple)
    page: int = 1
    page_size: int = 20


class ListAgentLogsUseCase:
    """List ``AgentExecution`` rows for the agent-logs API."""

    def __init__(self, s3_service: Optional[S3ServiceInterface] = None):
        # Optional so tests can swap in a fake without touching boto3.
        # A missing bucket configuration is non-fatal here — the use
        # case still returns rows, just without presigned URLs.
        if s3_service is not None:
            self._s3_service: Optional[S3ServiceInterface] = s3_service
        else:
            self._s3_service = self._build_default_s3_service()

    @staticmethod
    def _build_default_s3_service() -> Optional[S3ServiceInterface]:
        """Build the default S3 service or return ``None`` if unconfigured.

        Logs (rather than raises) on misconfiguration: the list
        endpoint should never 500 because traces storage is unreachable;
        rows without a presigned URL still render correctly.
        """
        try:
            bucket = resolve_traces_bucket()
        except Exception:
            logger.warning(
                "[AGENT_LOGS] No traces bucket configured; json_url will be null",
                exc_info=True,
            )
            return None
        try:
            return S3Service(bucket_name=bucket)
        except Exception:
            logger.warning(
                "[AGENT_LOGS] Failed to build S3Service; json_url will be null",
                exc_info=True,
            )
            return None

    def execute(self, dto: ListAgentLogsDTO) -> Tuple[List[AgentExecution], int]:
        """Run the query and return ``(rows, total)``.

        Total is computed before slicing so the client can compute
        ``has_more = page * page_size < total`` without fetching every
        page. Ordering is ``(-created_on, uuid)`` so two executions
        sharing the same ``created_on`` get a stable tiebreaker and a
        row never appears on two pages or skips a page. Each returned
        row carries a ``json_url`` attribute (``None`` when the row has
        no traces yet or S3 is unreachable) so the view layer renders
        with no S3 wiring.
        """
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

        queryset = queryset.order_by("-created_on", "uuid")

        total = queryset.count()
        page = max(dto.page, 1)
        page_size = max(dto.page_size, 1)
        offset = (page - 1) * page_size

        rows = list(queryset[offset : offset + page_size])  # noqa: E203
        for row in rows:
            row.json_url = self._presigned_url_for(row)
        return rows, total

    def _presigned_url_for(self, row: AgentExecution) -> Optional[str]:
        if not row.traces_s3_key or self._s3_service is None:
            return None
        try:
            return self._s3_service.generate_presigned_url(
                row.traces_s3_key, expiration=JSON_URL_TTL_SECONDS
            )
        except Exception:
            logger.warning(
                "[AGENT_LOGS] Failed to presign URL for execution %s",
                row.uuid,
                exc_info=True,
            )
            return None
