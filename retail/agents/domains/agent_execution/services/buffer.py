"""Redis-backed write buffer for agent execution traces.

The lifecycle invariant is "every UUID returned by ``start_execution`` has
a DB row from second zero, and is either in the flush queue ZSET or has
reached a terminal DB state". The flush task drains the ZSET; a periodic
SQL sweep finalises rows whose Redis state was lost (eviction, restart)
but whose DB row is still ``processing``.

Wire-up:

1. ``start_execution`` performs **one** DB INSERT (``status='processing'``)
   so the row is visible to ops immediately, then writes a small Redis
   hash (just ``updated_on``), the initial ``WEBHOOK_RECEIVED`` trace,
   and a ZSET entry keyed by ``now + max_wait_seconds``.
2. ``add_trace`` appends to the Redis trace list. No DB write.
3. ``update_metadata`` / ``update_status`` ``HSET`` fields on the Redis
   hash. When the status is terminal (``success`` / ``error`` / ``skip``)
   it also bumps the ZSET score to ``now`` so the next flush picks the
   execution up immediately. Non-terminal updates keep the original
   ``now + max_wait_seconds`` deadline.
4. The flush task (``ExecutionBufferService.flush``) drains the ZSET
   (terminals first, plus any non-terminal entries past their deadline),
   writes traces to S3 in parallel, applies a per-row UPDATE for
   terminal entries, a single batched UPDATE for timed-out entries, and
   unlinks Redis state.
5. Every Nth flush tick the same task additionally runs a SQL sweep:
   any row still ``status='processing'`` with ``updated_on`` older than
   the stuck threshold is force-finalised as ``error='Execution timed
   out'`` so a Redis outage cannot leave a row processing forever.
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple
from uuid import UUID, uuid4

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django_redis import get_redis_connection

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.types import ExecutionTraceType


logger = logging.getLogger(__name__)


def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


# Process-wide cache for the boto3-backed traces storage. Buffers are
# per-task; boto3.client("s3") is too expensive to build per task,
# so the storage instance is shared. Bucket-keyed so
# @override_settings(EXECUTION_TRACES_BUCKET=...) gets its own slot.
_shared_traces_storage: Dict[str, ExecutionTracesStorageService] = {}


def _get_shared_traces_storage() -> ExecutionTracesStorageService:
    bucket = getattr(settings, "EXECUTION_TRACES_BUCKET", None) or getattr(
        settings, "AWS_STORAGE_BUCKET_NAME", "test-bucket"
    )
    if bucket not in _shared_traces_storage:
        _shared_traces_storage[bucket] = ExecutionTracesStorageService()
    return _shared_traces_storage[bucket]


class ExecutionBufferService:
    """Eager-INSERT + batched-UPDATE buffer for agent executions."""

    DATA_KEY_PREFIX = "agent_execution:data:"
    TRACES_KEY_PREFIX = "agent_execution:traces:"
    FLUSH_QUEUE_KEY = "agent_execution:flush_queue"
    REDIS_TTL_SECONDS = 86_400

    DEFAULT_FLUSH_BATCH_SIZE = 500
    DEFAULT_MAX_WAIT_SECONDS = 600
    DEFAULT_STUCK_THRESHOLD_SECONDS = 600
    DEFAULT_S3_PARALLEL_PUTS = 10

    _TERMINAL_STATUSES = frozenset(
        {
            AgentExecutionStatus.SUCCESS,
            AgentExecutionStatus.ERROR,
            AgentExecutionStatus.SKIP,
        }
    )

    _TIMEOUT_ERROR_MESSAGE = "Execution timed out"

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
    # FK shortcuts. The buffer stores a UUID under the ``*_uuid`` field
    # name; the flush translates it to the model's ``*_id`` column so
    # Django persists it without a related-object lookup.
    _ORM_FK_TRANSLATIONS = {
        "integrated_agent_uuid": "integrated_agent_id",
        "template_uuid": "template_id",
        "broadcast_message_uuid": "broadcast_message_id",
    }

    _TYPED_INT_FIELDS = ("broadcast_id",)
    _TYPED_DECIMAL_FIELDS = ("amount",)

    def __init__(
        self,
        traces_storage: Optional[ExecutionTracesStorageService] = None,
    ):
        self._traces_storage = traces_storage
        self.flush_batch_size = getattr(
            settings,
            "AGENT_EXECUTION_FLUSH_BATCH_SIZE",
            self.DEFAULT_FLUSH_BATCH_SIZE,
        )
        self.max_wait_seconds = getattr(
            settings,
            "AGENT_EXECUTION_MAX_WAIT_SECONDS",
            self.DEFAULT_MAX_WAIT_SECONDS,
        )
        self.stuck_threshold_seconds = getattr(
            settings,
            "AGENT_EXECUTION_STUCK_THRESHOLD_SECONDS",
            self.DEFAULT_STUCK_THRESHOLD_SECONDS,
        )
        self.s3_parallel_puts = getattr(
            settings,
            "AGENT_EXECUTION_S3_PARALLEL_PUTS",
            self.DEFAULT_S3_PARALLEL_PUTS,
        )

    @property
    def traces_storage(self) -> ExecutionTracesStorageService:
        if self._traces_storage is None:
            self._traces_storage = _get_shared_traces_storage()
        return self._traces_storage

    def _data_key(self, execution_uuid) -> str:
        return f"{self.DATA_KEY_PREFIX}{execution_uuid}"

    def _traces_key(self, execution_uuid) -> str:
        return f"{self.TRACES_KEY_PREFIX}{execution_uuid}"

    def _is_terminal_status(self, status: Any) -> bool:
        if status is None:
            return False
        if isinstance(status, AgentExecutionStatus):
            status = status.value
        return status in self._TERMINAL_STATUSES

    def _serialize_value(self, value: Any) -> Optional[str]:
        if value is None:
            return None
        if isinstance(value, UUID):
            return str(value)
        if isinstance(value, Decimal):
            return str(value)
        if hasattr(value, "isoformat"):
            return value.isoformat()
        if isinstance(value, str):
            return value
        return str(value)

    def _serialize_fields(self, data: Dict[str, Any]) -> Dict[str, str]:
        """Convert a metadata dict into a Hash-storable mapping.

        ``None`` values are dropped so we don't pollute the Hash with
        empty entries; the deserialiser treats absent fields as
        ``None``. Without this, a terminal ``update_status(success)``
        with ``error_message=None`` would clobber an earlier
        ``error_message`` entry instead of preserving it.
        """
        out: Dict[str, str] = {}
        for key, value in data.items():
            encoded = self._serialize_value(value)
            if encoded is None:
                continue
            out[key] = encoded
        return out

    def _deserialize_hash(self, raw: Dict[Any, Any]) -> Dict[str, Any]:
        if not raw:
            return {}
        decoded: Dict[str, Any] = {}
        for k, v in raw.items():
            decoded[_decode(k)] = _decode(v)
        for field in self._TYPED_INT_FIELDS:
            if decoded.get(field) is not None:
                try:
                    decoded[field] = int(decoded[field])
                except (TypeError, ValueError):
                    decoded[field] = None
        for field in self._TYPED_DECIMAL_FIELDS:
            if decoded.get(field) is not None:
                try:
                    decoded[field] = Decimal(decoded[field])
                except Exception:
                    decoded[field] = None
        return decoded

    @staticmethod
    def _coerce_uuid(value: Any) -> Optional[UUID]:
        if value is None or value == "":
            return None
        if isinstance(value, UUID):
            return value
        try:
            return UUID(str(value))
        except (TypeError, ValueError):
            return None

    def start_execution(
        self,
        integrated_agent_uuid: Optional[UUID],
        contact_urn: str,
        webhook_payload: Dict[str, Any],
        order_id: Optional[str] = None,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
    ) -> UUID:
        """Create the DB row and seed Redis trace state.

        The DB INSERT is synchronous so ops can query the row the
        moment this returns. Trace state lives in Redis until the
        flush task picks the row up. If Redis is unreachable the row
        still lands in the DB; the SQL sweep finalises it later.
        """
        execution_uuid = uuid4()
        now = timezone.now()
        traces_s3_key = self.traces_storage.get_traces_key(execution_uuid)

        AgentExecution.objects.create(
            uuid=execution_uuid,
            integrated_agent_id=integrated_agent_uuid,
            contact_urn=contact_urn or "unknown",
            status=AgentExecutionStatus.PROCESSING,
            order_id=order_id,
            amount=amount,
            currency=currency,
            traces_s3_key=traces_s3_key,
        )

        initial_trace = {
            "type": ExecutionTraceType.WEBHOOK_RECEIVED.value,
            "timestamp": now.isoformat(),
            "data": webhook_payload,
        }

        try:
            redis_client = get_redis_connection("default")
            traces_key = self._traces_key(execution_uuid)
            data_key = self._data_key(execution_uuid)
            pipe = redis_client.pipeline(transaction=False)
            pipe.rpush(traces_key, json.dumps(initial_trace, ensure_ascii=False))
            pipe.expire(traces_key, self.REDIS_TTL_SECONDS)
            pipe.hset(data_key, mapping={"updated_on": now.isoformat()})
            pipe.expire(data_key, self.REDIS_TTL_SECONDS)
            pipe.zadd(
                self.FLUSH_QUEUE_KEY,
                {str(execution_uuid): now.timestamp() + self.max_wait_seconds},
            )
            pipe.execute()
        except Exception:
            # Row is in the DB; losing the Redis seed only loses the
            # initial trace and the deadline. The SQL sweep will pick
            # the row up after the stuck threshold.
            logger.exception(
                "[EXEC_LOG] Failed to seed Redis state for execution %s; "
                "row exists in DB and will be reconciled by the stuck sweep",
                execution_uuid,
            )

        logger.debug("Started execution %s", execution_uuid)
        return execution_uuid

    def add_trace(
        self,
        execution_uuid: UUID,
        trace_type: str,
        data: Dict[str, Any],
    ) -> bool:
        """Append a trace entry. Pure Redis."""
        now = timezone.now()
        trace = {
            "type": trace_type,
            "timestamp": now.isoformat(),
            "data": data,
        }
        try:
            redis_client = get_redis_connection("default")
            traces_key = self._traces_key(execution_uuid)
            data_key = self._data_key(execution_uuid)
            pipe = redis_client.pipeline(transaction=False)
            pipe.rpush(traces_key, json.dumps(trace, ensure_ascii=False))
            pipe.expire(traces_key, self.REDIS_TTL_SECONDS)
            pipe.hset(data_key, mapping={"updated_on": now.isoformat()})
            pipe.expire(data_key, self.REDIS_TTL_SECONDS)
            pipe.execute()
        except Exception:
            logger.exception(
                "[EXEC_LOG] Failed to append trace for execution %s "
                "(type=%s); trace dropped",
                execution_uuid,
                trace_type,
            )
            return False
        return True

    def update_metadata(
        self,
        execution_uuid: UUID,
        **fields: Any,
    ) -> bool:
        """Update one or more metadata fields on the Redis hash.

        Terminal status (``success`` / ``error`` / ``skip``) additionally
        ``ZADD``s the queue with score ``now`` so the next flush tick
        picks the execution up immediately. Non-terminal updates keep
        the original ``now + max_wait_seconds`` deadline.
        """
        if not fields:
            return False
        serialized = self._serialize_fields(fields)
        if not serialized:
            return False

        is_terminal = self._is_terminal_status(fields.get("status"))
        now = timezone.now()
        serialized["updated_on"] = now.isoformat()
        try:
            redis_client = get_redis_connection("default")
            data_key = self._data_key(execution_uuid)
            pipe = redis_client.pipeline(transaction=False)
            pipe.hset(data_key, mapping=serialized)
            pipe.expire(data_key, self.REDIS_TTL_SECONDS)
            if is_terminal:
                pipe.zadd(
                    self.FLUSH_QUEUE_KEY,
                    {str(execution_uuid): now.timestamp()},
                )
            pipe.execute()
        except Exception:
            logger.exception(
                "[EXEC_LOG] Failed to update metadata for execution %s",
                execution_uuid,
            )
            return False
        return True

    def update_status(
        self,
        execution_uuid: UUID,
        status: str,
        error_message: Optional[str] = None,
        template_uuid: Optional[UUID] = None,
        broadcast_id: Optional[int] = None,
        broadcast_message_uuid: Optional[UUID] = None,
    ) -> bool:
        return self.update_metadata(
            execution_uuid=execution_uuid,
            status=status,
            error_message=error_message,
            template_uuid=template_uuid,
            broadcast_id=broadcast_id,
            broadcast_message_uuid=broadcast_message_uuid,
        )

    def get_execution(self, execution_uuid: UUID) -> Optional[Dict[str, Any]]:
        """Read the live Redis hash. Used by tests and ops introspection.

        Returns ``None`` when the hash doesn't exist (already flushed
        or never seeded). Callers should fall back to a DB query for
        executions whose lifecycle has completed.
        """
        try:
            redis_client = get_redis_connection("default")
            raw = redis_client.hgetall(self._data_key(execution_uuid))
        except Exception:
            return None
        decoded = self._deserialize_hash(raw)
        return decoded or None

    def flush(self, do_stuck_sweep: bool = False) -> Dict[str, int]:
        """Drain the flush queue and persist to DB + S3.

        Args:
            do_stuck_sweep: When ``True``, additionally run the SQL
                stuck sweep that catches rows in ``processing`` past
                the stuck threshold. The flush task toggles this every
                Nth tick so the sweep fires periodically without
                running on every tick.

        Returns:
            ``{"flushed": int, "stuck_finalized": int}``.
        """
        try:
            redis_client = get_redis_connection("default")
        except Exception:
            logger.exception(
                "[EXEC_LOG] Could not connect to Redis; skipping flush tick"
            )
            return {"flushed": 0, "stuck_finalized": 0}

        now_ts = timezone.now().timestamp()
        try:
            ready_raw = (
                redis_client.zrangebyscore(
                    self.FLUSH_QUEUE_KEY,
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
            stuck_finalized = self._sweep_stuck_executions(redis_client)

        if flushed or stuck_finalized:
            logger.info(
                "[EXEC_LOG] Flushed %d execution(s); finalized %d stuck",
                flushed,
                stuck_finalized,
            )
        return {"flushed": flushed, "stuck_finalized": stuck_finalized}

    def _process_flush_batch(self, uuids: List[str], redis_client) -> int:
        if not uuids:
            return 0

        try:
            read_pipe = redis_client.pipeline(transaction=False)
            for u in uuids:
                read_pipe.hgetall(self._data_key(u))
                read_pipe.lrange(self._traces_key(u), 0, -1)
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
            data = self._deserialize_hash(raw_hash)
            traces = self._parse_traces(raw_traces, uuid_str)

            execution_uuid = UUID(uuid_str)
            traces_s3_key = data.get(
                "traces_s3_key"
            ) or self.traces_storage.get_traces_key(execution_uuid)

            if traces:
                s3_writes.append((execution_uuid, traces_s3_key, traces))

            if self._is_terminal_status(data.get("status")):
                terminal_entries.append((uuid_str, data))
            else:
                timeout_entries.append(uuid_str)

        s3_failures = self._write_traces_parallel(s3_writes)

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
                self._update_timeout_rows(timeout_entries)
        except Exception:
            logger.exception("[EXEC_LOG] DB update failed; leaving batch for next tick")
            return 0

        successful = [u for u, _ in terminal_entries] + timeout_entries
        if successful:
            try:
                cleanup_pipe = redis_client.pipeline(transaction=False)
                for u in successful:
                    cleanup_pipe.unlink(self._data_key(u), self._traces_key(u))
                cleanup_pipe.zrem(self.FLUSH_QUEUE_KEY, *successful)
                cleanup_pipe.execute()
            except Exception:
                logger.exception(
                    "[EXEC_LOG] Cleanup pipeline failed; some Redis state may linger"
                )

        return len(successful)

    def _write_traces_parallel(
        self,
        writes: List[Tuple[UUID, str, List[Dict[str, Any]]]],
    ) -> Set[str]:
        """Write a batch of traces files to S3 in parallel.

        Returns the set of UUID strings whose PUT failed so the caller
        can leave them in the flush queue for retry. A single-write
        batch skips the thread pool to avoid the executor overhead.
        """
        if not writes:
            return set()
        failures: Set[str] = set()

        def _put(
            execution_uuid: UUID, s3_key: str, traces: List[Dict[str, Any]]
        ) -> Optional[str]:
            try:
                self.traces_storage.write_traces(
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

        if len(writes) == 1:
            execution_uuid, s3_key, traces = writes[0]
            failed = _put(execution_uuid, s3_key, traces)
            if failed:
                failures.add(failed)
            return failures

        max_workers = max(1, min(self.s3_parallel_puts, len(writes)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_uuid = {
                executor.submit(_put, execution_uuid, s3_key, traces): str(
                    execution_uuid
                )
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

    def _update_terminal_rows(
        self,
        terminal_entries: List[Tuple[str, Dict[str, Any]]],
    ) -> None:
        """Per-row UPDATE for terminal-status executions.

        Each row gets its own ``filter(uuid=...).update(...)`` so we
        only touch the columns whose buffered hash carried a value.
        ``bulk_update`` would clobber missing fields with ``None`` —
        not safe when the buffer's hash is intentionally sparse.
        All UPDATEs run in the surrounding transaction so connection
        round-trips are amortised.
        """
        now = timezone.now()
        for uuid_str, data in terminal_entries:
            update_fields = self._extract_orm_fields(data)
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

    def _update_timeout_rows(self, uuid_strs: List[str]) -> None:
        """Mark deadline-expired non-terminal rows as ``error='timed out'``.

        A single SQL UPDATE collapses the whole batch. The
        ``status='processing'`` filter makes the call idempotent: a
        late terminal arriving after we picked the entry up but before
        the UPDATE hits won't be overwritten.
        """
        if not uuid_strs:
            return
        AgentExecution.objects.filter(
            uuid__in=[UUID(u) for u in uuid_strs],
            status=AgentExecutionStatus.PROCESSING,
        ).update(
            status=AgentExecutionStatus.ERROR,
            error_message=self._TIMEOUT_ERROR_MESSAGE,
            updated_on=timezone.now(),
        )

    def _extract_orm_fields(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Pick the kwargs from a Redis hash that map onto ``AgentExecution``.

        ``None`` and empty-string values are dropped so the UPDATE
        never clobbers an existing column with an absent value. FK
        shortcuts use the model's ``*_id`` form so Django stores the
        UUID directly without a related-object lookup.
        """
        out: Dict[str, Any] = {}
        for key in self._ORM_DIRECT_FIELDS:
            value = data.get(key)
            if value is None or value == "":
                continue
            out[key] = value
        for src, dst in self._ORM_FK_TRANSLATIONS.items():
            value = self._coerce_uuid(data.get(src))
            if value is not None:
                out[dst] = value
        return out

    def _parse_traces(
        self,
        raw_traces: Iterable[Any],
        uuid_str: str,
    ) -> List[Dict[str, Any]]:
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

    def _sweep_stuck_executions(self, redis_client) -> int:
        """Finalise rows still ``processing`` past the stuck threshold.

        Catches the rare case where Redis lost the ZSET entry (eviction,
        restart) but the DB row is still in flight. Best-effort flushes
        any leftover Redis traces to S3 first, then a single SQL UPDATE
        marks the rows as ``error='Execution timed out'``.
        """
        cutoff = timezone.now() - timedelta(seconds=self.stuck_threshold_seconds)
        stuck = list(
            AgentExecution.objects.filter(
                status=AgentExecutionStatus.PROCESSING,
                updated_on__lt=cutoff,
            ).values_list("uuid", "traces_s3_key")[: self.flush_batch_size]
        )
        if not stuck:
            return 0

        s3_writes: List[Tuple[UUID, str, List[Dict[str, Any]]]] = []
        cleanup_keys: List[str] = []
        for execution_uuid, traces_s3_key in stuck:
            cleanup_keys.append(self._data_key(execution_uuid))
            cleanup_keys.append(self._traces_key(execution_uuid))
            try:
                traces_raw = redis_client.lrange(
                    self._traces_key(execution_uuid), 0, -1
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
                        self._parse_traces(traces_raw, str(execution_uuid)),
                    )
                )

        # Best-effort: a partial S3 failure here doesn't block the
        # finalisation, the row would otherwise stay processing forever.
        self._write_traces_parallel(s3_writes)

        AgentExecution.objects.filter(
            uuid__in=[u for u, _ in stuck],
            status=AgentExecutionStatus.PROCESSING,
        ).update(
            status=AgentExecutionStatus.ERROR,
            error_message=self._TIMEOUT_ERROR_MESSAGE,
            updated_on=timezone.now(),
        )

        try:
            cleanup_pipe = redis_client.pipeline(transaction=False)
            cleanup_pipe.unlink(*cleanup_keys)
            cleanup_pipe.zrem(
                self.FLUSH_QUEUE_KEY,
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
