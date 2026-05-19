"""Finalise rows still ``processing`` past the stuck threshold.

Catches the rare case where Redis lost the ZSET entry (eviction,
restart) but the DB row is still in flight. Best-effort flushes any
leftover Redis traces to S3 first, then marks the rows as
``error='Execution timed out'`` so a Redis outage cannot leave a row
processing forever.
"""

import logging
from datetime import timedelta
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from django.conf import settings
from django.utils import timezone

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
    _get_shared_traces_storage,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)


logger = logging.getLogger(__name__)


class SweepStuckExecutionsUseCase:
    """Mark rows stuck in ``processing`` as timed-out."""

    def __init__(
        self,
        traces_storage: Optional[ExecutionTracesStorageService] = None,
        stuck_threshold_seconds: Optional[int] = None,
        batch_size: Optional[int] = None,
        s3_parallel_puts: Optional[int] = None,
    ):
        self._traces_storage = traces_storage
        self.stuck_threshold_seconds = (
            stuck_threshold_seconds
            if stuck_threshold_seconds is not None
            else getattr(
                settings,
                "AGENT_EXECUTION_STUCK_THRESHOLD_SECONDS",
                ExecutionBufferService.DEFAULT_STUCK_THRESHOLD_SECONDS,
            )
        )
        self.batch_size = (
            batch_size
            if batch_size is not None
            else getattr(
                settings,
                "AGENT_EXECUTION_FLUSH_BATCH_SIZE",
                ExecutionBufferService.DEFAULT_FLUSH_BATCH_SIZE,
            )
        )
        self.s3_parallel_puts = (
            s3_parallel_puts
            if s3_parallel_puts is not None
            else getattr(
                settings,
                "AGENT_EXECUTION_S3_PARALLEL_PUTS",
                ExecutionBufferService.DEFAULT_S3_PARALLEL_PUTS,
            )
        )

    @property
    def traces_storage(self) -> ExecutionTracesStorageService:
        if self._traces_storage is None:
            self._traces_storage = _get_shared_traces_storage()
        return self._traces_storage

    def execute(self, redis_client) -> int:
        # Imported lazily to avoid a circular import between
        # flush_executions and this module.
        from retail.agents.domains.agent_execution.usecases.flush_executions import (
            _parse_traces,
            mark_processing_as_timed_out,
            write_traces_parallel,
        )

        cutoff = timezone.now() - timedelta(seconds=self.stuck_threshold_seconds)
        stuck = list(
            AgentExecution.objects.filter(
                status=AgentExecutionStatus.PROCESSING,
                updated_on__lt=cutoff,
            ).values_list("uuid", "traces_s3_key")[: self.batch_size]
        )
        if not stuck:
            return 0

        s3_writes: List[Tuple[UUID, str, List[Dict[str, Any]]]] = []
        cleanup_keys: List[str] = []
        for execution_uuid, traces_s3_key in stuck:
            cleanup_keys.append(ExecutionBufferService.data_key(execution_uuid))
            cleanup_keys.append(ExecutionBufferService.traces_key(execution_uuid))
            try:
                traces_raw = redis_client.lrange(
                    ExecutionBufferService.traces_key(execution_uuid), 0, -1
                )
            except Exception:
                traces_raw = []
            if traces_raw:
                key = traces_s3_key or self.traces_storage.get_traces_key(
                    execution_uuid
                )
                s3_writes.append(
                    (
                        execution_uuid,
                        key,
                        _parse_traces(traces_raw, str(execution_uuid)),
                    )
                )

        # Best-effort: a partial S3 failure here doesn't block the
        # finalisation; the row would otherwise stay processing forever.
        write_traces_parallel(self.traces_storage, s3_writes, self.s3_parallel_puts)

        mark_processing_as_timed_out(u for u, _ in stuck)

        try:
            cleanup_pipe = redis_client.pipeline(transaction=False)
            cleanup_pipe.unlink(*cleanup_keys)
            cleanup_pipe.zrem(
                ExecutionBufferService.FLUSH_QUEUE_KEY,
                *[str(u) for u, _ in stuck],
            )
            cleanup_pipe.execute()
        except Exception:
            logger.exception(
                "[EXEC_LOG] Stuck-sweep cleanup pipeline failed; remnants may linger"
            )

        logger.warning(
            "[EXEC_LOG] Stuck sweep finalised %d execution(s) past the threshold",
            len(stuck),
        )
        return len(stuck)
