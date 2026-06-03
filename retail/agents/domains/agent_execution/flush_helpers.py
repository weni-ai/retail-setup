"""Shared helpers for draining the agent-execution buffer.

Holds the trace parsing, timeout finalisation, and parallel S3 write
primitives used by both
:class:`retail.agents.domains.agent_execution.usecases.flush_executions.FlushExecutionsUseCase`
and
:class:`retail.agents.domains.agent_execution.usecases.sweep_stuck_executions.SweepStuckExecutionsUseCase`.

Lives at the domain root (alongside ``row_mapper`` / ``task_helpers``)
rather than under ``usecases/`` because it is a set of shared helper
functions, not a use case. It must not import from ``flush_executions``
or ``sweep_stuck_executions`` so both can import it at the top without
a circular dependency.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import UUID

from django.utils import timezone

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)


logger = logging.getLogger(__name__)


TIMEOUT_ERROR_MESSAGE = "Execution timed out"


def parse_traces(raw_traces: Iterable[Any], uuid_str: str) -> List[Dict[str, Any]]:
    traces: List[Dict[str, Any]] = []
    for raw_trace in raw_traces or []:
        if isinstance(raw_trace, bytes):
            raw_trace = raw_trace.decode("utf-8")
        try:
            traces.append(json.loads(raw_trace))
        except json.JSONDecodeError as parse_err:
            logger.warning(
                "[EXEC_LOG] Skipping malformed trace for %s: %s",
                uuid_str,
                parse_err,
            )
    return traces


def mark_processing_as_timed_out(uuids: Iterable[UUID]) -> None:
    """Mark in-flight rows as ``error='Execution timed out'``.

    The ``status='processing'`` filter makes the call idempotent: a
    late terminal arriving after the caller picked the UUIDs up but
    before this UPDATE hits won't be overwritten.
    """
    uuid_list = list(uuids)
    if not uuid_list:
        return
    AgentExecution.objects.filter(
        uuid__in=uuid_list,
        status=AgentExecutionStatus.PROCESSING,
    ).update(
        status=AgentExecutionStatus.ERROR,
        error_message=TIMEOUT_ERROR_MESSAGE,
        updated_on=timezone.now(),
    )


def write_traces_parallel(
    traces_storage: ExecutionTracesStorageService,
    writes: List[Tuple[UUID, str, List[Dict[str, Any]]]],
    max_workers: int,
) -> Set[str]:
    """Write a batch of traces files to S3 in parallel.

    Returns the set of UUID strings whose PUT failed so the caller can
    leave them in the flush queue for retry.
    """
    if not writes:
        return set()

    failures: Set[str] = set()

    def _put(execution_uuid: UUID, s3_key: str, traces: List[Dict[str, Any]]) -> Optional[str]:
        try:
            traces_storage.write_traces(
                execution_uuid=execution_uuid,
                traces=traces,
                s3_key=s3_key,
            )
            return None
        except Exception:
            logger.exception(
                "[EXEC_LOG] S3 PUT failed for execution %s; will retry",
                execution_uuid,
            )
            return str(execution_uuid)

    workers = max(1, min(max_workers, len(writes)))
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_uuid = {
            executor.submit(_put, execution_uuid, s3_key, traces): str(execution_uuid)
            for execution_uuid, s3_key, traces in writes
        }
        for future, uuid_str in future_to_uuid.items():
            try:
                failed = future.result()
            except Exception:
                logger.exception(
                    "[EXEC_LOG] Unexpected S3 PUT failure for %s", uuid_str
                )
                failed = uuid_str
            if failed:
                failures.add(failed)
    return failures
