"""Use case: consolidated delivered/converted counts for a project or agent."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone as dt_timezone
from typing import Optional
from uuid import UUID

from retail.broadcasts.models import (
    BroadcastConversion,
    BroadcastMessage,
    BroadcastStatus,
)


@dataclass(frozen=True)
class GetBroadcastSummaryDTO:
    """Input for ``GetBroadcastSummaryUseCase``.

    When ``integrated_agent_uuid`` is omitted, totals aggregate every
    dispatch/conversion in the project. When set, both counts are scoped
    to that integrated agent.

    ``delivered`` counts dispatches whose status reached the device
    (``delivered`` or ``read``) within the dispatch date range.
    ``converted`` counts ``BroadcastConversion`` rows within the conversion
    date range.
    """

    project_uuid: UUID
    start_date: date
    end_date: date
    integrated_agent_uuid: Optional[UUID] = None


@dataclass(frozen=True)
class BroadcastSummaryResult:
    delivered: int
    converted: int


class GetBroadcastSummaryUseCase:
    """Return delivered and converted totals for a project or integrated agent."""

    _DELIVERED_STATUSES = (BroadcastStatus.DELIVERED, BroadcastStatus.READ)

    def execute(self, dto: GetBroadcastSummaryDTO) -> BroadcastSummaryResult:
        start_dt = datetime.combine(dto.start_date, time.min, tzinfo=dt_timezone.utc)
        end_dt = datetime.combine(dto.end_date, time.max, tzinfo=dt_timezone.utc)

        delivered_qs = BroadcastMessage.objects.filter(
            project__uuid=dto.project_uuid,
            created_at__range=(start_dt, end_dt),
            status__in=self._DELIVERED_STATUSES,
        )
        converted_qs = BroadcastConversion.objects.filter(
            project__uuid=dto.project_uuid,
            converted_at__range=(start_dt, end_dt),
        )

        if dto.integrated_agent_uuid is not None:
            delivered_qs = delivered_qs.filter(
                integrated_agent__uuid=dto.integrated_agent_uuid
            )
            converted_qs = converted_qs.filter(
                integrated_agent__uuid=dto.integrated_agent_uuid
            )

        return BroadcastSummaryResult(
            delivered=delivered_qs.count(),
            converted=converted_qs.count(),
        )
