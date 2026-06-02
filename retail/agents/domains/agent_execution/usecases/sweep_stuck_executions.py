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
from redis import Redis
from redis.exceptions import RedisError

from retail.agents.domains.agent_execution.flush_helpers import (
    mark_processing_as_timed_out,
    parse_traces,
    write_traces_parallel,
)
from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services import buffer as _buffer_module
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
    get_shared_traces_storage,
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
        redis_client: Optional[Redis] = None,
    ):
        self._traces_storage = traces_storage
        self._redis_client = redis_client
        self.stuck_threshold_seconds = self._resolve(
            stuck_threshold_seconds,
            "AGENT_EXECUTION_STUCK_THRESHOLD_SECONDS",
            ExecutionBufferService.DEFAULT_STUCK_THRESHOLD_SECONDS,
        )
        self.batch_size = self._resolve(
            batch_size,
            "AGENT_EXECUTION_FLUSH_BATCH_SIZE",
            ExecutionBufferService.DEFAULT_FLUSH_BATCH_SIZE,
        )
        self.s3_parallel_puts = self._resolve(
            s3_parallel_puts,
            "AGENT_EXECUTION_S3_PARALLEL_PUTS",
            ExecutionBufferService.DEFAULT_S3_PARALLEL_PUTS,
        )

    @staticmethod
    def _resolve(explicit: Optional[int], setting_name: str, default: int) -> int:
        if explicit is not None:
            return explicit
        return getattr(settings, setting_name, default)

    @property
    def traces_storage(self) -> ExecutionTracesStorageService:
        if self._traces_storage is None:
            self._traces_storage = get_shared_traces_storage()
        return self._traces_storage

    @property
    def redis_client(self) -> Redis:
        if self._redis_client is None:
            self._redis_client = _buffer_module.get_redis_connection("default")
        return self._redis_client

    def execute(self) -> int:
        cutoff = timezone.now() - timedelta(seconds=self.stuck_threshold_seconds)
        stuck = list(
            AgentExecution.objects.filter(
                status=AgentExecutionStatus.PROCESSING,
                updated_on__lt=cutoff,
            ).values_list("uuid", "traces_s3_key")[: self.batch_size]
        )
        if not stuck:
            return 0

        redis_client = self.redis_client
        s3_writes: List[Tuple[UUID, str, List[Dict[str, Any]]]] = []
        cleanup_keys: List[str] = []
        for execution_uuid, traces_s3_key in stuck:
            cleanup_keys.append(ExecutionBufferService.data_key(execution_uuid))
            cleanup_keys.append(ExecutionBufferService.traces_key(execution_uuid))
            try:
                traces_raw = redis_client.lrange(
                    ExecutionBufferService.traces_key(execution_uuid), 0, -1
                )
            except RedisError:
                traces_raw = []
            if traces_raw:
                key = traces_s3_key or self.traces_storage.get_traces_key(
                    execution_uuid
                )
                s3_writes.append(
                    (
                        execution_uuid,
                        key,
                        parse_traces(traces_raw, str(execution_uuid)),
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
        except RedisError:
            logger.exception(
                "[EXEC_LOG] Stuck-sweep cleanup pipeline failed; remnants may linger"
            )

        logger.warning(
            f"[EXEC_LOG] Stuck sweep finalised {len(stuck)} execution(s) "
            f"past the threshold"
        )
        return len(stuck)
