"""Use case: paginated query over AgentExecution rows.

Wraps the common analytics query patterns behind a use case so future
views, admin actions, and CLI tools call into one place. Keeps the
model purely a persistence concern.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional
from uuid import UUID

from retail.agents.domains.agent_execution.models import AgentExecution


@dataclass(frozen=True)
class ListExecutionsFilter:
    """Filter and pagination input for ``ListExecutionsUseCase``.

    All fields are optional; ``execute`` only narrows the queryset by
    fields the caller actually sets. Defaults pick a small page size
    so a misuse can't accidentally pull a million rows.
    """

    integrated_agent_uuid: Optional[UUID] = None
    contact_urn: Optional[str] = None
    status: Optional[str] = None
    created_after: Optional[datetime] = None
    created_before: Optional[datetime] = None
    limit: int = 50
    offset: int = 0


class ListExecutionsUseCase:
    """List ``AgentExecution`` rows with filters and pagination."""

    def execute(self, dto: ListExecutionsFilter) -> List[AgentExecution]:
        queryset = AgentExecution.objects.all()

        if dto.integrated_agent_uuid is not None:
            queryset = queryset.filter(integrated_agent_id=dto.integrated_agent_uuid)
        if dto.contact_urn is not None:
            queryset = queryset.filter(contact_urn=dto.contact_urn)
        if dto.status is not None:
            queryset = queryset.filter(status=dto.status)
        if dto.created_after is not None:
            queryset = queryset.filter(created_on__gte=dto.created_after)
        if dto.created_before is not None:
            queryset = queryset.filter(created_on__lte=dto.created_before)

        offset = max(dto.offset, 0)
        limit = max(dto.limit, 0)
        return list(queryset[offset : offset + limit])  # noqa: E203
