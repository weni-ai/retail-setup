"""Use case: load traces for one or more agent executions.

Replaces the magic ``AgentExecution.traces`` property, which used to
do an S3 GET behind a Python attribute access. The use case keeps the
S3 IO explicit at the call site, exposes a batch helper so listing
views don't iterate by hand, and short-circuits to an empty list when
an execution has no ``traces_s3_key`` so we never hit S3 for rows
that didn't make it through flush.
"""

import logging
from typing import Any, Dict, Iterable, List, Optional, Union
from uuid import UUID

from django.core.exceptions import ValidationError

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)


logger = logging.getLogger(__name__)


class FetchTracesUseCase:
    """Resolve trace payloads for an execution or a batch of executions."""

    def __init__(
        self,
        traces_storage: Optional[ExecutionTracesStorageService] = None,
    ):
        self.traces_storage = traces_storage or ExecutionTracesStorageService()

    def execute(self, execution: AgentExecution) -> List[Dict[str, Any]]:
        """Fetch traces for an execution we already have in memory.

        Returns ``[]`` when the row has no S3 key yet — this happens
        when the buffer hasn't flushed yet or when the row was
        persisted before the S3-backed storage shipped.
        """
        if not execution.traces_s3_key:
            return []

        return self.traces_storage.get_traces(
            execution.uuid, s3_key=execution.traces_s3_key
        )

    def execute_for_uuid(
        self, execution_uuid: Union[UUID, str]
    ) -> List[Dict[str, Any]]:
        """Look up an execution by UUID and fetch its traces.

        Never raises: returns ``[]`` for missing rows so view code
        can treat "no row", "no traces", and "malformed UUID" the
        same way. Django raises ``ValidationError`` for strings that
        can't be parsed as a UUID (and ``ValueError`` when callers
        hand us something ``uuid.UUID()`` chokes on) — both are
        funneled into the same empty-list return so the URL dispatcher
        can forward arbitrary path segments without this use case
        becoming a 500 vector.
        """
        try:
            execution = AgentExecution.objects.get(uuid=execution_uuid)
        except (AgentExecution.DoesNotExist, ValidationError, ValueError):
            return []
        return self.execute(execution)

    def execute_batch(
        self, executions: Iterable[AgentExecution]
    ) -> Dict[UUID, List[Dict[str, Any]]]:
        """Fetch traces for a batch of executions.

        S3 has no batch GET API, so the helper still issues one
        ``get_traces`` call per execution — its purpose is to give
        callers a single shape (``{uuid: traces}``) without each one
        iterating by hand.
        """
        return {execution.uuid: self.execute(execution) for execution in executions}
