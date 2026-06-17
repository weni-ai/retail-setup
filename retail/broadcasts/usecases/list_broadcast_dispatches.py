"""Use case: paginated broadcast dispatch report for a project."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone as dt_timezone
from typing import List, Optional, Tuple
from uuid import UUID

from django.db.models import Exists, OuterRef, Subquery

from retail.broadcasts.models import BroadcastConversion, BroadcastMessage


@dataclass(frozen=True)
class ListBroadcastDispatchesDTO:
    """Input for ``ListBroadcastDispatchesUseCase``.

    ``project_uuid`` scopes every row to a single tenant. When
    ``integrated_agent_uuid`` is set, results are further restricted to
    dispatches from that integrated agent. The date range filters on
    ``BroadcastMessage.created_at`` (dispatch time), inclusive on both
    calendar days in UTC.
    """

    project_uuid: UUID
    start_date: date
    end_date: date
    integrated_agent_uuid: Optional[UUID] = None
    page: int = 1
    page_size: int = 20


@dataclass(frozen=True)
class BroadcastDispatchRow:
    """One broadcast dispatch row for the report API."""

    contact_urn: str
    order_id: Optional[str]
    status: str
    converted: bool
    dispatched_at: datetime
    converted_at: Optional[datetime]


class ListBroadcastDispatchesUseCase:
    """List broadcast dispatches with conversion attribution flags."""

    def execute(
        self, dto: ListBroadcastDispatchesDTO
    ) -> Tuple[List[BroadcastDispatchRow], int]:
        start_dt = datetime.combine(dto.start_date, time.min, tzinfo=dt_timezone.utc)
        end_dt = datetime.combine(dto.end_date, time.max, tzinfo=dt_timezone.utc)

        conversion_at_subquery = BroadcastConversion.objects.filter(
            broadcast_id=OuterRef("pk")
        ).values("converted_at")[:1]

        queryset = BroadcastMessage.objects.filter(
            project__uuid=dto.project_uuid,
            created_at__range=(start_dt, end_dt),
        )
        if dto.integrated_agent_uuid is not None:
            queryset = queryset.filter(integrated_agent__uuid=dto.integrated_agent_uuid)

        queryset = queryset.annotate(
            is_converted=Exists(
                BroadcastConversion.objects.filter(broadcast_id=OuterRef("pk"))
            ),
            conversion_converted_at=Subquery(conversion_at_subquery),
        ).order_by("-created_at", "uuid")

        total = queryset.count()
        page = max(dto.page, 1)
        page_size = max(dto.page_size, 1)
        offset = (page - 1) * page_size

        rows = [
            BroadcastDispatchRow(
                contact_urn=message.contact_urn,
                order_id=message.order_id,
                status=message.status,
                converted=message.is_converted,
                dispatched_at=message.created_at,
                converted_at=message.conversion_converted_at,
            )
            for message in queryset[offset : offset + page_size]  # noqa: E203
        ]
        return rows, total
