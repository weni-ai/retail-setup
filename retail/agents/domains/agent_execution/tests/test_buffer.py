"""Buffer service contract tests.

The buffer's eager-INSERT + batched-UPDATE design creates the
``AgentExecution`` row immediately on ``start_execution`` and persists
all subsequent state changes in batches via ``flush``. These tests pin
the per-method contract: what each method writes (and doesn't write)
to Redis and Postgres, and that the full happy-path lifecycle ends
with exactly one DB row, exactly one S3 PUT, and clean Redis state.
"""

import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import UUID, uuid4

from django.test import TestCase, override_settings

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.buffer import (
    ExecutionBufferService,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.tests._fakes import (
    FakeRedisConnection,
    FakeS3Client,
)
from retail.agents.domains.agent_execution.types import ExecutionTraceType


@override_settings(EXECUTION_TRACES_BUCKET="test-traces-bucket")
class ExecutionBufferServiceTests(TestCase):
    def setUp(self):
        super().setUp()
        self.fake_redis = FakeRedisConnection()
        self.fake_s3 = FakeS3Client(bucket_name="test-traces-bucket")
        self.traces_storage = ExecutionTracesStorageService(s3_service=self.fake_s3)

        patcher = patch(
            "retail.agents.domains.agent_execution.services.buffer."
            "get_redis_connection",
            return_value=self.fake_redis,
        )
        patcher.start()
        self.addCleanup(patcher.stop)

        self.buffer = ExecutionBufferService(traces_storage=self.traces_storage)

    def _data_key(self, execution_uuid: UUID) -> str:
        return f"{self.buffer.DATA_KEY_PREFIX}{execution_uuid}"

    def _traces_key(self, execution_uuid: UUID) -> str:
        return f"{self.buffer.TRACES_KEY_PREFIX}{execution_uuid}"

    # ------------------------------------------------------------------
    # start_execution
    # ------------------------------------------------------------------

    def test_start_execution_creates_db_row_at_processing(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="whatsapp:+5511999999999",
            webhook_payload={"order_id": "abc"},
            order_id="abc",
            amount=Decimal("199.99"),
            currency="BRL",
        )

        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.status, AgentExecutionStatus.PROCESSING)
        self.assertEqual(row.contact_urn, "whatsapp:+5511999999999")
        self.assertIsNone(row.integrated_agent_id)
        self.assertEqual(row.order_id, "abc")
        self.assertEqual(row.amount, Decimal("199.99"))
        self.assertEqual(row.currency, "BRL")
        self.assertEqual(
            row.traces_s3_key,
            self.traces_storage.get_traces_key(execution_uuid),
        )

    def test_start_execution_does_not_touch_s3(self):
        """An S3 outage must not block a webhook from being recorded."""
        self.fake_s3.fail_on_put = True
        self.fake_s3.fail_on_get = True

        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="whatsapp:+5511999999999",
            webhook_payload={"order_id": "abc"},
        )

        self.assertIsInstance(execution_uuid, UUID)
        self.assertEqual(self.fake_s3.put_calls, [])
        self.assertEqual(self.fake_s3.get_calls, [])
        self.assertTrue(
            AgentExecution.objects.filter(uuid=execution_uuid).exists(),
            "DB row must exist even when S3 is unreachable",
        )

    def test_start_execution_seeds_initial_trace_in_redis_list(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="whatsapp:+5511999999999",
            webhook_payload={"order_id": "abc"},
        )

        traces_raw = self.fake_redis.lrange(self._traces_key(execution_uuid), 0, -1)
        self.assertEqual(len(traces_raw), 1)
        initial_trace = json.loads(traces_raw[0])
        self.assertEqual(
            initial_trace["type"], ExecutionTraceType.WEBHOOK_RECEIVED.value
        )
        self.assertEqual(initial_trace["data"]["order_id"], "abc")

    def test_start_execution_pushes_zset_entry_with_max_wait_deadline(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )

        score = self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid))
        self.assertIsNotNone(
            score,
            "start_execution must enqueue the UUID with a deadline so the "
            "flush task can finalise it even if no terminal status arrives",
        )

    def test_start_execution_unknown_contact_urn_falls_back(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="",
            webhook_payload={},
        )
        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.contact_urn, "unknown")

    def test_start_execution_redis_failure_keeps_db_row(self):
        """A Redis outage at start time must not prevent the DB row.

        The SQL stuck sweep would otherwise have nothing to recover.
        """
        with patch.object(
            self.fake_redis, "pipeline", side_effect=RuntimeError("redis down")
        ):
            execution_uuid = self.buffer.start_execution(
                integrated_agent_uuid=None,
                contact_urn="unknown",
                webhook_payload={},
            )
        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.status, AgentExecutionStatus.PROCESSING)

    def test_start_execution_serializes_extended_types_in_webhook_payload(self):
        """DRF/Kombu can deliver datetime / Decimal / UUID in the payload.

        The OrderStatus webhook is the canonical offender: its
        ``OrderStatusSerializer`` validates ``currentChangeDate`` and
        ``lastChangeDate`` into Python ``datetime`` objects, and Kombu's
        typed JSON envelope rehydrates them on the worker side. The
        stdlib ``json.dumps`` used here previously raised ``TypeError``
        and aborted the whole pipeline before ``pipe.execute()``,
        leaving the row to be force-finalised as ``Execution timed
        out`` by the stuck sweep. The buffer must encode these
        ``DjangoJSONEncoder``-friendly types as JSON strings instead.
        """
        order_uuid = UUID("04f2b26f-2f34-4b55-a37c-4ead2cd67bcf")
        webhook_payload = {
            "domain": "Marketplace",
            "currentChangeDate": datetime(2026, 5, 12, 18, 20, 0),
            "lastChangeDate": datetime(2026, 5, 12, 18, 20, 0, tzinfo=timezone.utc),
            "amount": Decimal("19.99"),
            "id": order_uuid,
        }

        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload=webhook_payload,
        )

        traces_raw = self.fake_redis.lrange(self._traces_key(execution_uuid), 0, -1)
        self.assertEqual(len(traces_raw), 1)
        decoded = json.loads(traces_raw[0])
        self.assertEqual(decoded["type"], ExecutionTraceType.WEBHOOK_RECEIVED.value)
        data = decoded["data"]
        self.assertEqual(data["domain"], "Marketplace")
        self.assertEqual(data["currentChangeDate"], "2026-05-12T18:20:00")
        self.assertEqual(data["lastChangeDate"], "2026-05-12T18:20:00Z")
        self.assertEqual(data["amount"], "19.99")
        self.assertEqual(data["id"], str(order_uuid))

        self.assertIsNotNone(
            self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid)),
            "pipe.execute() must run to completion when the payload "
            "carries datetime/Decimal/UUID values",
        )

    # ------------------------------------------------------------------
    # add_trace
    # ------------------------------------------------------------------

    def test_add_trace_appends_to_redis_list_only(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        before_calls = len(self.fake_s3.put_calls)

        ok = self.buffer.add_trace(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.LAMBDA_REQUEST.value,
            data={"params": {"x": 1}},
        )

        self.assertTrue(ok)
        self.assertEqual(len(self.fake_s3.put_calls), before_calls)
        traces_raw = self.fake_redis.lrange(self._traces_key(execution_uuid), 0, -1)
        self.assertEqual(len(traces_raw), 2)
        appended = json.loads(traces_raw[1])
        self.assertEqual(appended["type"], "lambda_request")

    def test_add_trace_for_unknown_uuid_does_not_query_db(self):
        """Trace appends are pure Redis. Bogus UUIDs cost a TTL'd list, no DB."""
        rogue_uuid = uuid4()
        with self.assertNumQueries(0):
            ok = self.buffer.add_trace(
                execution_uuid=rogue_uuid,
                trace_type="lambda_request",
                data={"x": 1},
            )
        self.assertTrue(ok)

    def test_add_trace_serializes_extended_types_in_data(self):
        """``add_trace`` accepts the same DjangoJSONEncoder-friendly types.

        Error traces from ``task_order_status_update`` reuse the raw
        ``order_update_data`` (with its rehydrated datetimes) as
        ``error_data``; lambda / broadcast responses can carry
        ``Decimal`` totals. The buffer must encode them all without
        dropping the trace.
        """
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        order_uuid = UUID("04f2b26f-2f34-4b55-a37c-4ead2cd67bcf")

        ok = self.buffer.add_trace(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.LAMBDA_RESPONSE.value,
            data={
                "order_amount": Decimal("19.99"),
                "completed_at": datetime(2026, 5, 12, 18, 20, 0),
                "ref": order_uuid,
            },
        )

        self.assertTrue(ok)
        traces_raw = self.fake_redis.lrange(self._traces_key(execution_uuid), 0, -1)
        self.assertEqual(len(traces_raw), 2)
        appended = json.loads(traces_raw[1])
        self.assertEqual(appended["type"], "lambda_response")
        self.assertEqual(appended["data"]["order_amount"], "19.99")
        self.assertEqual(appended["data"]["completed_at"], "2026-05-12T18:20:00")
        self.assertEqual(appended["data"]["ref"], str(order_uuid))

    # ------------------------------------------------------------------
    # update_metadata / update_status
    # ------------------------------------------------------------------

    def test_update_metadata_writes_only_named_fields_to_hash(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid,
            contact_urn="whatsapp:+5511777777777",
        )

        bucket = self.fake_redis.hashes[self._data_key(execution_uuid)]
        self.assertEqual(bucket[b"contact_urn"], b"whatsapp:+5511777777777")
        self.assertNotIn(b"status", bucket)

    def test_update_metadata_drops_none_values(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        result = self.buffer.update_metadata(
            execution_uuid=execution_uuid,
            error_message=None,
            template_uuid=None,
        )
        self.assertFalse(result)
        bucket = self.fake_redis.hashes.get(self._data_key(execution_uuid), {})
        self.assertNotIn(b"error_message", bucket)
        self.assertNotIn(b"template_uuid", bucket)

    def test_update_metadata_returns_false_when_no_fields(self):
        self.assertFalse(self.buffer.update_metadata(execution_uuid=uuid4()))

    def test_update_status_terminal_bumps_zset_score_to_now(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        before = self.fake_redis.zscore(
            self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid)
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
            broadcast_id=42,
        )
        after = self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid))
        self.assertIsNotNone(after)
        self.assertLess(
            after,
            before,
            "Terminal status must lower the deadline so the next flush "
            "picks the execution up immediately",
        )

    def test_update_metadata_non_terminal_does_not_touch_zset(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        before = self.fake_redis.zscore(
            self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid)
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid,
            contact_urn="whatsapp:+5511777777777",
        )
        after = self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid))
        self.assertEqual(before, after)

    def test_update_status_processing_does_not_enqueue(self):
        """Calling update_status with the initial status is defensive — never enqueue."""
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        before = self.fake_redis.zscore(
            self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid)
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.PROCESSING,
        )
        after = self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid))
        self.assertEqual(before, after)

    # ------------------------------------------------------------------
    # Full happy-path lifecycle
    # ------------------------------------------------------------------

    def test_full_lifecycle_ends_with_one_db_update_one_s3_put(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="whatsapp:+5511999999999",
            webhook_payload={"order_id": "abc"},
            order_id="abc",
            amount=Decimal("199.99"),
            currency="BRL",
        )
        self.buffer.add_trace(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.LAMBDA_REQUEST.value,
            data={"params": {"x": 1}},
        )
        self.buffer.add_trace(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.LAMBDA_RESPONSE.value,
            data={"status": 0},
        )
        self.buffer.add_trace(
            execution_uuid=execution_uuid,
            trace_type=ExecutionTraceType.BROADCAST_RESPONSE.value,
            data={"id": 42},
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
            broadcast_id=42,
        )

        result = self.buffer.flush()

        self.assertEqual(result["flushed"], 1)
        self.assertEqual(result["stuck_finalized"], 0)
        self.assertEqual(len(self.fake_s3.put_calls), 1)
        s3_payload = json.loads(self.fake_s3.put_calls[0]["content"].decode("utf-8"))
        self.assertEqual(len(s3_payload), 4)
        self.assertEqual(
            [t["type"] for t in s3_payload],
            [
                "webhook_received",
                "lambda_request",
                "lambda_response",
                "broadcast_response",
            ],
        )

        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.status, AgentExecutionStatus.SUCCESS)
        self.assertEqual(row.broadcast_id, 42)
        self.assertEqual(row.contact_urn, "whatsapp:+5511999999999")

    def test_update_status_persists_broadcast_message_uuid_as_fk(self):
        """``broadcast_message_uuid`` flows through the Hash and is
        translated to the ``broadcast_message_id`` column at flush
        time, linking the AgentExecution row to the BroadcastMessage
        persisted by ``RecordBroadcastSentUseCase`` at dispatch."""
        from retail.agents.domains.agent_integration.models import IntegratedAgent
        from retail.agents.domains.agent_management.models import Agent
        from retail.broadcasts.models import BroadcastMessage, BroadcastStatus
        from retail.projects.models import Project

        project = Project.objects.create(name="P", uuid=uuid4())
        agent = Agent.objects.create(
            uuid=uuid4(),
            name="A",
            slug="a",
            description="",
            project=project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=agent, project=project
        )
        broadcast_message = BroadcastMessage.objects.create(
            project=project,
            integrated_agent=integrated_agent,
            status=BroadcastStatus.SENT,
        )

        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=integrated_agent.uuid,
            contact_urn="whatsapp:+5511999999999",
            webhook_payload={},
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
            broadcast_id=42,
            broadcast_message_uuid=broadcast_message.uuid,
        )

        self.buffer.flush()

        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.broadcast_message_id, broadcast_message.uuid)
        self.assertEqual(row.broadcast_id, 42)

    def test_flush_unlinks_redis_state_after_success(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
        )

        self.buffer.flush()

        self.assertNotIn(self._data_key(execution_uuid), self.fake_redis.hashes)
        self.assertNotIn(self._traces_key(execution_uuid), self.fake_redis.lists)
        self.assertIsNone(
            self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid))
        )

    def test_get_execution_returns_live_redis_hash(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_metadata(
            execution_uuid=execution_uuid,
            contact_urn="whatsapp:+5511777777777",
        )

        data = self.buffer.get_execution(execution_uuid)
        self.assertIsNotNone(data)
        self.assertEqual(data["contact_urn"], "whatsapp:+5511777777777")

    def test_get_execution_returns_none_when_redis_state_gone(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
        )
        self.buffer.flush()

        self.assertIsNone(self.buffer.get_execution(execution_uuid))
