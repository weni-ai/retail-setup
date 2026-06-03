"""Redis-backed write buffer for agent execution traces.

The buffer owns per-execution state during a webhook's lifetime:

1. ``start_execution`` performs **one** DB INSERT (``status='processing'``)
   so the row is visible to ops immediately, then writes a small Redis
   hash (just ``updated_on``), the initial ``WEBHOOK_RECEIVED`` trace,
   and a ZSET entry keyed by ``now + max_wait_seconds``.
2. ``add_trace`` appends to the Redis trace list. No DB write.
3. ``update_metadata`` ``HSET``s fields on the Redis hash. When the
   status is terminal (``success`` / ``error`` / ``skip``) it also
   bumps the ZSET score to ``now`` so the next flush tick picks the
   execution up immediately.

Flush + sweep are use cases that consume this adapter:

- :class:`retail.agents.domains.agent_execution.usecases.flush_executions.FlushExecutionsUseCase`
  drains the ZSET (terminals first, plus any non-terminal entries
  past their deadline), writes traces to S3 in parallel, and applies
  the DB UPDATEs.
- :class:`retail.agents.domains.agent_execution.usecases.sweep_stuck_executions.SweepStuckExecutionsUseCase`
  finalises rows whose Redis state was lost (eviction, restart) but
  whose DB row is still ``processing``.
"""

import functools
import json
import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID, uuid4

from django.conf import settings
from django.core.serializers.json import DjangoJSONEncoder
from django.utils import timezone
from django_redis import get_redis_connection
from redis.exceptions import RedisError

from retail.agents.domains.agent_execution.constants import UNKNOWN_CONTACT_URN
from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
    resolve_traces_bucket,
)
from retail.agents.domains.agent_execution.types import ExecutionTraceType
from retail.interfaces.services.execution_buffer import ExecutionBufferInterface


logger = logging.getLogger(__name__)


def _decode(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return value


@functools.lru_cache(maxsize=4)
def _traces_storage_for(bucket: str) -> ExecutionTracesStorageService:
    """Per-bucket cache so boto3.client("s3") is built once per process."""
    return ExecutionTracesStorageService()


def get_shared_traces_storage() -> ExecutionTracesStorageService:
    """Return the process-wide traces storage instance.

    Bucket-keyed so ``@override_settings(EXECUTION_TRACES_BUCKET=...)``
    in tests gets its own slot instead of latching onto the first
    bucket the process saw.
    """
    return _traces_storage_for(resolve_traces_bucket())


class ExecutionBufferService(ExecutionBufferInterface):
    """Redis adapter for the agent execution buffer.

    Owns the Redis hash + traces list + flush-queue ZSET. The DB
    INSERT on ``start_execution`` is performed here too so the row is
    visible to ops immediately; later persistence (S3 + DB UPDATE)
    happens in the flush use case.
    """

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

    _TYPED_INT_FIELDS = ("broadcast_id",)
    _TYPED_DECIMAL_FIELDS = ("amount",)

    def __init__(
        self,
        traces_storage: Optional[ExecutionTracesStorageService] = None,
    ):
        self._traces_storage = traces_storage
        self.max_wait_seconds = getattr(
            settings,
            "AGENT_EXECUTION_MAX_WAIT_SECONDS",
            self.DEFAULT_MAX_WAIT_SECONDS,
        )

    @property
    def traces_storage(self) -> ExecutionTracesStorageService:
        if self._traces_storage is None:
            self._traces_storage = get_shared_traces_storage()
        return self._traces_storage

    @classmethod
    def data_key(cls, execution_uuid) -> str:
        return f"{cls.DATA_KEY_PREFIX}{execution_uuid}"

    @classmethod
    def traces_key(cls, execution_uuid) -> str:
        return f"{cls.TRACES_KEY_PREFIX}{execution_uuid}"

    # Kept for backwards-compatible diagnostic scripts; prefer the
    # classmethods above.
    def _data_key(self, execution_uuid) -> str:
        return self.data_key(execution_uuid)

    def _traces_key(self, execution_uuid) -> str:
        return self.traces_key(execution_uuid)

    @classmethod
    def is_terminal_status(cls, status: Any) -> bool:
        if status is None:
            return False
        if isinstance(status, AgentExecutionStatus):
            status = status.value
        return status in cls._TERMINAL_STATUSES

    @staticmethod
    def _encode_trace(trace: Dict[str, Any]) -> str:
        """Serialize a trace using Django's extended JSON encoder.

        Worker-side payloads can carry datetime / Decimal / UUID values
        that Kombu's typed envelope rehydrates from upstream producers
        (DRF serializers, VTEX webhooks, etc.). Standardising on
        ``DjangoJSONEncoder`` here keeps a truly exotic type from
        breaking the buffer without forcing every caller to pre-encode.
        """
        return json.dumps(trace, ensure_ascii=False, cls=DjangoJSONEncoder)

    @staticmethod
    def _serialize_value(value: Any) -> Optional[str]:
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

        ``None`` values are dropped so the Hash isn't polluted with
        empty entries; the deserialiser treats absent fields as
        ``None``. Without this, a terminal ``update_metadata(status=success)``
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

    def deserialize_hash(self, raw: Dict[Any, Any]) -> Dict[str, Any]:
        """Decode and type-coerce a raw Redis hash mapping.

        Public because the flush use case round-trips a hash through
        this method to recover typed int / Decimal columns before
        applying the DB UPDATE.
        """
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
        self._create_execution_row(
            execution_uuid=execution_uuid,
            integrated_agent_uuid=integrated_agent_uuid,
            contact_urn=contact_urn,
            order_id=order_id,
            amount=amount,
            currency=currency,
        )
        self._seed_redis_trace_state(
            execution_uuid=execution_uuid,
            webhook_payload=webhook_payload,
        )
        logger.debug(f"Started execution {execution_uuid}")
        return execution_uuid

    def _create_execution_row(
        self,
        *,
        execution_uuid: UUID,
        integrated_agent_uuid: Optional[UUID],
        contact_urn: str,
        order_id: Optional[str],
        amount: Optional[Decimal],
        currency: Optional[str],
    ) -> None:
        """Insert the ``AgentExecution`` row at ``status='processing'``."""
        traces_s3_key = self.traces_storage.get_traces_key(execution_uuid)
        AgentExecution.objects.create(
            uuid=execution_uuid,
            integrated_agent_id=integrated_agent_uuid,
            contact_urn=contact_urn or UNKNOWN_CONTACT_URN,
            status=AgentExecutionStatus.PROCESSING,
            order_id=order_id,
            amount=amount,
            currency=currency,
            traces_s3_key=traces_s3_key,
        )

    def _seed_redis_trace_state(
        self,
        *,
        execution_uuid: UUID,
        webhook_payload: Dict[str, Any],
    ) -> None:
        """Seed Redis with the initial trace, hash, and flush deadline.

        Best-effort: if Redis is unreachable, the DB row created
        upstream is reconciled later by the SQL stuck sweep, so losing
        the Redis seed only drops the initial trace and the deadline
        rather than the execution itself.
        """
        now = timezone.now()
        initial_trace = {
            "type": ExecutionTraceType.WEBHOOK_RECEIVED.value,
            "timestamp": now.isoformat(),
            "data": webhook_payload,
        }
        try:
            redis_client = get_redis_connection("default")
            traces_key = self.traces_key(execution_uuid)
            data_key = self.data_key(execution_uuid)
            pipe = redis_client.pipeline(transaction=False)
            pipe.rpush(traces_key, self._encode_trace(initial_trace))
            pipe.expire(traces_key, self.REDIS_TTL_SECONDS)
            pipe.hset(data_key, mapping={"updated_on": now.isoformat()})
            pipe.expire(data_key, self.REDIS_TTL_SECONDS)
            pipe.zadd(
                self.FLUSH_QUEUE_KEY,
                {str(execution_uuid): now.timestamp() + self.max_wait_seconds},
            )
            pipe.execute()
        except RedisError:
            logger.exception(
                f"[EXEC_LOG] Failed to seed Redis state for execution {execution_uuid}; "
                f"row exists in DB and will be reconciled by the stuck sweep"
            )

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
            traces_key = self.traces_key(execution_uuid)
            data_key = self.data_key(execution_uuid)
            pipe = redis_client.pipeline(transaction=False)
            pipe.rpush(traces_key, self._encode_trace(trace))
            pipe.expire(traces_key, self.REDIS_TTL_SECONDS)
            pipe.hset(data_key, mapping={"updated_on": now.isoformat()})
            pipe.expire(data_key, self.REDIS_TTL_SECONDS)
            pipe.execute()
        except RedisError:
            logger.exception(
                f"[EXEC_LOG] Failed to append trace for execution {execution_uuid} "
                f"(type={trace_type}); trace dropped"
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

        is_terminal = self.is_terminal_status(fields.get("status"))
        now = timezone.now()
        serialized["updated_on"] = now.isoformat()
        try:
            redis_client = get_redis_connection("default")
            data_key = self.data_key(execution_uuid)
            pipe = redis_client.pipeline(transaction=False)
            pipe.hset(data_key, mapping=serialized)
            pipe.expire(data_key, self.REDIS_TTL_SECONDS)
            if is_terminal:
                pipe.zadd(
                    self.FLUSH_QUEUE_KEY,
                    {str(execution_uuid): now.timestamp()},
                )
            pipe.execute()
        except RedisError:
            logger.exception(
                f"[EXEC_LOG] Failed to update metadata for execution {execution_uuid}"
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
        """Convenience wrapper kept for backwards compatibility.

        New code should call :meth:`update_metadata` directly with the
        relevant keyword arguments.
        """
        return self.update_metadata(
            execution_uuid=execution_uuid,
            status=status,
            error_message=error_message,
            template_uuid=template_uuid,
            broadcast_id=broadcast_id,
            broadcast_message_uuid=broadcast_message_uuid,
        )

    def get_execution(self, execution_uuid: UUID) -> Optional[Dict[str, Any]]:
        """Read the live Redis hash. Diagnostic-only.

        Returns ``None`` when the hash doesn't exist (already flushed
        or never seeded). Callers should fall back to a DB query for
        executions whose lifecycle has completed.
        """
        try:
            redis_client = get_redis_connection("default")
            raw = redis_client.hgetall(self.data_key(execution_uuid))
        except RedisError:
            return None
        decoded = self.deserialize_hash(raw)
        return decoded or None
