"""Use case: single-execution lookup by UUID.

Returns ``None`` for missing rows so callers can treat "row absent"
and "row not yet flushed" the same way without juggling a try/except
around every read. Malformed UUIDs are treated the same as a missing
row — Django raises ``ValidationError`` for bad strings and
``ValueError`` when ``uuid.UUID()`` is called directly, so both are
swallowed here instead of bubbling up to the view layer.
"""

from typing import Optional, Union
from uuid import UUID

from django.core.exceptions import ValidationError

from retail.agents.domains.agent_execution.models import AgentExecution


class RetrieveExecutionUseCase:
    """Fetch a single ``AgentExecution`` by UUID."""

    def execute(self, execution_uuid: Union[UUID, str]) -> Optional[AgentExecution]:
        try:
            return AgentExecution.objects.get(uuid=execution_uuid)
        except (AgentExecution.DoesNotExist, ValidationError, ValueError):
            return None
