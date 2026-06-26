"""Flush the agent-execution buffer to Postgres and S3.

Drains the Redis ZSET in ``ExecutionBufferService.FLUSH_QUEUE_KEY``,
writes traces to S3 in parallel, applies per-row UPDATEs for terminal
entries and a single batched UPDATE for timed-out entries, then
unlinks the Redis state. Optionally runs the SQL stuck sweep on the
same tick — that lives in ``SweepStuckExecutionsUseCase``.
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_execution.flush_helpers import (
    mark_processing_as_timed_out,
    parse_traces,
    write_traces_parallel,
)
from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.services import buffer as _buffer_module
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
    _decode,
    get_shared_traces_storage,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.usecases.sweep_stuck_executions import (
    SweepStuckExecutionsUseCase,
)


logger = logging.getLogger(__name__)


# Redis hash field -> AgentExecution column. Only fields that map
# 1:1 onto the model land here. The flush extracts these from the
# deserialized hash and feeds them straight into ``update(...)``.
_ORM_DIRECT_FIELDS: Tuple[str, ...] = (
    "status",
    "error_message",
    "contact_urn",
    "broadcast_id",
    "order_id",
    "amount",
    "currency",
    "traces_s3_key",
)

# FK shortcuts. The buffer stores UUIDs under ``*_uuid`` field names;
# the flush translates them to the model's ``*_id`` columns. Integrated
# agent ids are integer PKs; template and broadcast_message ids remain
# UUIDs (legacy PK / to_field).
_ORM_FK_TRANSLATIONS = {
    "integrated_agent_uuid": "integrated_agent_id",
    "template_uuid": "template_id",
    "broadcast_message_uuid": "broadcast_message_id",
}


def _collect_integrated_agent_uuids(
    entries: List[Tuple[str, Dict[str, Any]]],
) -> set[UUID]:
    uuids: set[UUID] = set()
    for _, data in entries:
        agent_uuid = _coerce_uuid(data.get("integrated_agent_uuid"))
        if agent_uuid is not None:
            uuids.add(agent_uuid)
    return uuids


def _build_integrated_agent_pk_map(uuids: set[UUID]) -> Dict[UUID, int]:
    if not uuids:
        return {}
    return {
        agent_uuid: pk
        for agent_uuid, pk in IntegratedAgent.objects.filter(
            uuid__in=uuids
        ).values_list("uuid", "pk")
    }


def _coerce_uuid(value: Any) -> Optional[UUID]:
    if value is None or value == "":
        return None
    if isinstance(value, UUID):
        return value
    try:
        return UUID(str(value))
    except (TypeError, ValueError):
        return None


def _extract_orm_fields(
    data: Dict[str, Any],
    *,
    integrated_agent_pk_map: Dict[UUID, int],
) -> Dict[str, Any]:
    """Pick the kwargs from a Redis hash that map onto ``AgentExecution``.

    ``None`` and empty-string values are dropped so the UPDATE never
    clobbers an existing column with an absent value. FK shortcuts map
    buffer UUIDs onto the ORM ``*_id`` columns (integer for integrated
    agent, UUID for template and broadcast_message).
    """
    out: Dict[str, Any] = {}
    for key in _ORM_DIRECT_FIELDS:
        value = data.get(key)
        if value is None or value == "":
            continue
        out[key] = value
    for src, dst in _ORM_FK_TRANSLATIONS.items():
        if src == "integrated_agent_uuid":
            agent_uuid = _coerce_uuid(data.get(src))
            if agent_uuid is not None:
                resolved_pk = integrated_agent_pk_map.get(agent_uuid)
                if resolved_pk is not None:
                    out[dst] = resolved_pk
            continue
        value = _coerce_uuid(data.get(src))
        if value is not None:
            out[dst] = value
    return out


@dataclass(frozen=True)
class FlushResult:
    """Outcome of a single flush tick."""

    flushed: int = 0
    stuck_finalized: int = 0

    def as_dict(self) -> Dict[str, int]:
        """Backwards-compatible dict view for callers expecting the old shape."""
        return {"flushed": self.flushed, "stuck_finalized": self.stuck_finalized}


class FlushExecutionsUseCase:
    """Drain the execution buffer to DB + S3."""

    def __init__(
        self,
        buffer: Optional[ExecutionBufferService] = None,
        traces_storage: Optional[ExecutionTracesStorageService] = None,
        sweep_use_case: Optional[SweepStuckExecutionsUseCase] = None,
    ):
        self.buffer = buffer or ExecutionBufferService(traces_storage=traces_storage)
        self._traces_storage = traces_storage
        self.sweep_use_case = sweep_use_case
        self.flush_batch_size = getattr(
            settings,
            "AGENT_EXECUTION_FLUSH_BATCH_SIZE",
            ExecutionBufferService.DEFAULT_FLUSH_BATCH_SIZE,
        )
        self.s3_parallel_puts = getattr(
            settings,
            "AGENT_EXECUTION_S3_PARALLEL_PUTS",
            ExecutionBufferService.DEFAULT_S3_PARALLEL_PUTS,
        )

    @property
    def traces_storage(self) -> ExecutionTracesStorageService:
        if self._traces_storage is None:
            self._traces_storage = get_shared_traces_storage()
        return self._traces_storage

    def execute(self, do_stuck_sweep: bool = False) -> FlushResult:
        """Drain the flush queue and optionally run the stuck sweep."""
        try:
            # Route through the buffer module so a single
            # ``patch("...buffer.get_redis_connection", ...)`` in tests
            # covers both the buffer adapter and this use case.
            redis_client = _buffer_module.get_redis_connection("default")
        except Exception:
            logger.exception(
                "[EXEC_LOG] Could not connect to Redis; skipping flush tick"
            )
            return FlushResult()

        now_ts = timezone.now().timestamp()
        try:
            ready_raw = (
                redis_client.zrangebyscore(
                    ExecutionBufferService.FLUSH_QUEUE_KEY,
                    min=0,
                    max=now_ts,
                    start=0,
                    num=self.flush_batch_size,
                )
                or []
            )
        except Exception:
            logger.exception(
                "[EXEC_LOG] ZRANGEBYSCORE failed on flush queue; skipping tick"
            )
            ready_raw = []

        flushed = 0
        if ready_raw:
            ready = [_decode(u) for u in ready_raw]
            flushed = self._process_flush_batch(ready, redis_client)

        stuck_finalized = 0
        if do_stuck_sweep:
            sweep = self.sweep_use_case or SweepStuckExecutionsUseCase(
                traces_storage=self.traces_storage,
                batch_size=self.flush_batch_size,
                s3_parallel_puts=self.s3_parallel_puts,
                redis_client=redis_client,
            )
            stuck_finalized = sweep.execute()

        if flushed or stuck_finalized:
            logger.info(
                "[EXEC_LOG] Flushed %d execution(s); finalized %d stuck",
                flushed,
                stuck_finalized,
            )
        return FlushResult(flushed=flushed, stuck_finalized=stuck_finalized)

    def _process_flush_batch(self, uuids: List[str], redis_client) -> int:
        if not uuids:
            return 0

        try:
            read_pipe = redis_client.pipeline(transaction=False)
            for u in uuids:
                read_pipe.hgetall(self.buffer.data_key(u))
                read_pipe.lrange(self.buffer.traces_key(u), 0, -1)
            read_results = read_pipe.execute()
        except Exception:
            logger.exception(
                "[EXEC_LOG] Pipelined read failed; leaving batch for next tick"
            )
            return 0

        terminal_entries: List[Tuple[str, Dict[str, Any]]] = []
        timeout_entries: List[str] = []
        s3_writes: List[Tuple[UUID, str, List[Dict[str, Any]]]] = []

        for i, uuid_str in enumerate(uuids):
            raw_hash = read_results[i * 2]
            raw_traces = read_results[i * 2 + 1]
            data = self.buffer.deserialize_hash(raw_hash)
            traces = parse_traces(raw_traces, uuid_str)

            execution_uuid = UUID(uuid_str)
            traces_s3_key = data.get(
                "traces_s3_key"
            ) or self.traces_storage.get_traces_key(execution_uuid)

            if traces:
                s3_writes.append((execution_uuid, traces_s3_key, traces))

            if self.buffer.is_terminal_status(data.get("status")):
                terminal_entries.append((uuid_str, data))
            else:
                timeout_entries.append(uuid_str)

        s3_failures = write_traces_parallel(
            self.traces_storage, s3_writes, self.s3_parallel_puts
        )

        # Anything whose S3 PUT failed stays in the queue so the next
        # tick retries. The DB UPDATE is correlated to the S3 write
        # because the row carries the traces_s3_key, and we don't want
        # to mark a row as terminal while its trace file is still
        # pending.
        if s3_failures:
            terminal_entries = [
                (u, d) for u, d in terminal_entries if u not in s3_failures
            ]
            timeout_entries = [u for u in timeout_entries if u not in s3_failures]

        try:
            with transaction.atomic():
                self._update_terminal_rows(terminal_entries)
                mark_processing_as_timed_out(UUID(u) for u in timeout_entries)
        except Exception:
            logger.exception("[EXEC_LOG] DB update failed; leaving batch for next tick")
            return 0

        successful = [u for u, _ in terminal_entries] + timeout_entries
        if successful:
            try:
                cleanup_pipe = redis_client.pipeline(transaction=False)
                for u in successful:
                    cleanup_pipe.unlink(
                        self.buffer.data_key(u), self.buffer.traces_key(u)
                    )
                cleanup_pipe.zrem(ExecutionBufferService.FLUSH_QUEUE_KEY, *successful)
                cleanup_pipe.execute()
            except Exception:
                logger.exception(
                    "[EXEC_LOG] Cleanup pipeline failed; some Redis state may linger"
                )

        return len(successful)

    @staticmethod
    def _update_terminal_rows(
        terminal_entries: List[Tuple[str, Dict[str, Any]]],
    ) -> None:
        """Per-row UPDATE for terminal-status executions.

        Each row gets its own ``filter(uuid=...).update(...)`` so we
        only touch the columns whose buffered hash carried a value.
        ``bulk_update`` would clobber missing fields with ``None`` —
        not safe when the buffer's hash is intentionally sparse.
        """
        now = timezone.now()
        integrated_agent_pk_map = _build_integrated_agent_pk_map(
            _collect_integrated_agent_uuids(terminal_entries)
        )
        for uuid_str, data in terminal_entries:
            update_fields = _extract_orm_fields(
                data,
                integrated_agent_pk_map=integrated_agent_pk_map,
            )
            if not update_fields:
                continue
            update_fields["updated_on"] = now
            updated = AgentExecution.objects.filter(uuid=UUID(uuid_str)).update(
                **update_fields
            )
            if not updated:
                logger.warning(
                    "[EXEC_LOG] Terminal flush found no DB row for execution %s; "
                    "fields=%s",
                    uuid_str,
                    sorted(update_fields.keys()),
                )
