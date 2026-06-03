"""Use case: paginated agent-logs query for the public API.

Surface tailored to the agent-logs API: page/page_size + total instead of
limit/offset, ILIKE search across contact_urn / order_id, multi-status
and multi-template OR filters, and an inclusive ``start_date``/``end_date``
calendar-day range.

Trace payloads are no longer surfaced as presigned S3 URLs here: the
row only advertises ``has_json`` and the client fetches the payload
through the proxy endpoint (``GET /logs/{log_uuid}/json/``), so this
use case never touches S3.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone as dt_timezone
from typing import List, Optional, Sequence, Tuple
from uuid import UUID

from django.db.models import Q

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.status_mapping import (
    build_status_filter,
)


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
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    template_uuids: Sequence[UUID] = field(default_factory=tuple)
    statuses: Sequence[str] = field(default_factory=tuple)
    page: int = 1
    page_size: int = 20


class ListAgentLogsUseCase:
    """List ``AgentExecution`` rows for the agent-logs API."""

    def execute(self, dto: ListAgentLogsDTO) -> Tuple[List[AgentExecution], int]:
        """Run the query and return ``(rows, total)``.

        Total is computed before slicing so the client can compute
        ``has_more = page * page_size < total`` without fetching every
        page. Ordering is ``(-created_on, uuid)`` so two executions
        sharing the same ``created_on`` get a stable tiebreaker and a
        row never appears on two pages or skips a page.
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

        queryset = queryset.order_by("-created_on", "uuid")

        total = queryset.count()
        page = max(dto.page, 1)
        page_size = max(dto.page_size, 1)
        offset = (page - 1) * page_size

        rows = list(queryset[offset : offset + page_size])  # noqa: E203
        return rows, total
