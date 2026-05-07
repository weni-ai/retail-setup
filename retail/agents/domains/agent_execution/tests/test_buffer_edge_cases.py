"""Defensive branch coverage for ``ExecutionBufferService``.

Things that should be tolerated without taking the consumer down:

- ``add_trace`` / ``update_metadata`` no-op when fields are empty or
  Redis is unreachable instead of raising.
- ``flush`` survives a Redis read failure, an S3 PUT failure
  (entries stay in the queue for retry), and a DB UPDATE failure
  (entries stay in the queue for retry).
- The cleanup pipeline on the flush task tolerates Redis failures.
- Malformed traces in the Redis list are skipped, not fatal.
"""

import json
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


@override_settings(EXECUTION_TRACES_BUCKET="test-traces-bucket")
class BufferEdgeCaseTests(TestCase):
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
    # Defensive bails
    # ------------------------------------------------------------------

    def test_update_metadata_returns_false_when_every_field_is_none(self):
        before = self.fake_redis.pipeline_execute_count
        self.assertFalse(
            self.buffer.update_metadata(
                execution_uuid=uuid4(), error_message=None, template_uuid=None
            )
        )
        self.assertEqual(self.fake_redis.pipeline_execute_count, before)

    def test_update_metadata_returns_false_when_called_with_no_kwargs(self):
        self.assertFalse(self.buffer.update_metadata(execution_uuid=uuid4()))

    def test_add_trace_returns_false_when_redis_pipeline_raises(self):
        with patch.object(
            self.fake_redis, "pipeline", side_effect=RuntimeError("redis down")
        ):
            ok = self.buffer.add_trace(
                execution_uuid=uuid4(), trace_type="lambda_request", data={"x": 1}
            )
        self.assertFalse(ok)

    def test_update_metadata_returns_false_when_redis_pipeline_raises(self):
        with patch.object(
            self.fake_redis, "pipeline", side_effect=RuntimeError("redis down")
        ):
            ok = self.buffer.update_metadata(
                execution_uuid=uuid4(), contact_urn="whatsapp:+1"
            )
        self.assertFalse(ok)

    def test_get_execution_returns_none_on_redis_failure(self):
        with patch.object(
            self.fake_redis, "hgetall", side_effect=RuntimeError("redis down")
        ):
            self.assertIsNone(self.buffer.get_execution(uuid4()))

    # ------------------------------------------------------------------
    # Flush resilience
    # ------------------------------------------------------------------

    def test_flush_with_no_queue_entries_is_noop(self):
        result = self.buffer.flush()
        self.assertEqual(result, {"flushed": 0, "stuck_finalized": 0})
        self.assertEqual(self.fake_s3.put_calls, [])

    def test_flush_handles_zrangebyscore_failure_and_returns_zero(self):
        with patch.object(
            self.fake_redis,
            "zrangebyscore",
            side_effect=RuntimeError("redis down"),
        ):
            result = self.buffer.flush()
        self.assertEqual(result, {"flushed": 0, "stuck_finalized": 0})

    def test_flush_handles_redis_connect_failure(self):
        with patch(
            "retail.agents.domains.agent_execution.services.buffer."
            "get_redis_connection",
            side_effect=RuntimeError("connection refused"),
        ):
            result = self.buffer.flush()
        self.assertEqual(result, {"flushed": 0, "stuck_finalized": 0})

    def test_flush_leaves_entries_in_queue_when_s3_put_fails(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={"k": "v"},
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
        )
        self.fake_s3.fail_on_put = True

        result = self.buffer.flush()

        self.assertEqual(result["flushed"], 0)
        # Entry stays in the queue so the next tick retries
        self.assertIsNotNone(
            self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(execution_uuid))
        )
        # DB row stays at processing because we never persisted the terminal
        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.status, AgentExecutionStatus.PROCESSING)

    def test_flush_skips_malformed_traces_without_failing_the_batch(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={"k": "v"},
        )
        # Inject a malformed trace alongside the good initial one
        self.fake_redis.lists[self._traces_key(execution_uuid)].append(b"{not valid")

        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
        )
        result = self.buffer.flush()

        self.assertEqual(result["flushed"], 1)
        self.assertEqual(len(self.fake_s3.put_calls), 1)
        body = json.loads(self.fake_s3.put_calls[0]["content"].decode("utf-8"))
        # Only the initial good trace survived; the malformed one was dropped
        self.assertEqual(len(body), 1)
        self.assertEqual(body[0]["type"], "webhook_received")

    def test_flush_handles_db_update_failure_without_unlinking_redis(self):
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        self.buffer.update_status(
            execution_uuid=execution_uuid,
            status=AgentExecutionStatus.SUCCESS,
        )
        with patch(
            "retail.agents.domains.agent_execution.services.buffer."
            "AgentExecution.objects"
        ) as mock_objects:
            mock_objects.filter.side_effect = RuntimeError("db down")
            result = self.buffer.flush()

        self.assertEqual(result["flushed"], 0)
        # Redis state is preserved so next tick retries
        self.assertIn(self._data_key(execution_uuid), self.fake_redis.hashes)

    def test_flush_unknown_uuid_in_queue_is_logged_and_continues(self):
        """A queue entry for a UUID with no DB row warns but doesn't crash."""
        rogue_uuid = uuid4()
        self.fake_redis.zadd(self.buffer.FLUSH_QUEUE_KEY, {str(rogue_uuid): 0})
        self.fake_redis.hashes[self._data_key(rogue_uuid)] = {
            b"status": AgentExecutionStatus.SUCCESS.encode("utf-8"),
        }

        result = self.buffer.flush()

        # Bulk update finds no row but the batch still completes
        self.assertEqual(result["flushed"], 1)
        # The queue entry is gone (we don't keep retrying a UUID that
        # has no row to update)
        self.assertIsNone(
            self.fake_redis.zscore(self.buffer.FLUSH_QUEUE_KEY, str(rogue_uuid))
        )
