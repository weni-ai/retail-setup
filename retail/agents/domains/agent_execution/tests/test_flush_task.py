"""Flush task integration tests.

The Celery task wrapper, the deadline-expired finalisation flow, the
periodic SQL sweep, parallel S3 PUTs, and the beat schedule shape all
live here. The single-method behaviour of the buffer is covered in
``test_buffer.py``; this file pins the wiring between
``task_flush_execution_logs``, the buffer's ``flush``, and the
underlying DB / S3 / Redis state.
"""

from datetime import timedelta
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

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
from retail.agents.tasks import (
    _FLUSH_TICK_KEY,
    task_flush_execution_logs,
)


@override_settings(EXECUTION_TRACES_BUCKET="test-traces-bucket")
class FlushTaskWrapperTests(TestCase):
    """The thin Celery wrapper around ``ExecutionBufferService.flush``."""

    def test_task_calls_buffer_flush_and_returns_its_result(self):
        with patch(
            "retail.agents.tasks.ExecutionBufferService"
        ) as mock_buffer_cls, patch(
            "retail.agents.tasks._next_flush_tick", return_value=1
        ):
            mock_buffer = MagicMock()
            mock_buffer.flush.return_value = {"flushed": 3, "stuck_finalized": 0}
            mock_buffer_cls.return_value = mock_buffer

            result = task_flush_execution_logs.run()

        self.assertEqual(result, {"flushed": 3, "stuck_finalized": 0})
        mock_buffer.flush.assert_called_once()

    @override_settings(AGENT_EXECUTION_STUCK_SWEEP_EVERY_N_TICKS=10)
    def test_task_triggers_stuck_sweep_every_nth_tick(self):
        with patch(
            "retail.agents.tasks.ExecutionBufferService"
        ) as mock_buffer_cls, patch(
            "retail.agents.tasks._next_flush_tick", return_value=10
        ):
            mock_buffer = MagicMock()
            mock_buffer.flush.return_value = {"flushed": 0, "stuck_finalized": 1}
            mock_buffer_cls.return_value = mock_buffer

            task_flush_execution_logs.run()

        mock_buffer.flush.assert_called_once_with(do_stuck_sweep=True)

    @override_settings(AGENT_EXECUTION_STUCK_SWEEP_EVERY_N_TICKS=10)
    def test_task_skips_sweep_when_tick_is_not_a_multiple(self):
        with patch(
            "retail.agents.tasks.ExecutionBufferService"
        ) as mock_buffer_cls, patch(
            "retail.agents.tasks._next_flush_tick", return_value=3
        ):
            mock_buffer = MagicMock()
            mock_buffer.flush.return_value = {"flushed": 0, "stuck_finalized": 0}
            mock_buffer_cls.return_value = mock_buffer

            task_flush_execution_logs.run()

        mock_buffer.flush.assert_called_once_with(do_stuck_sweep=False)

    def test_task_skips_sweep_when_tick_counter_is_unavailable(self):
        """``_next_flush_tick`` returns 0 on Redis failure, which never
        satisfies ``tick % N == 0`` for the real cadence."""
        with patch(
            "retail.agents.tasks.ExecutionBufferService"
        ) as mock_buffer_cls, patch(
            "retail.agents.tasks._next_flush_tick", return_value=0
        ):
            mock_buffer = MagicMock()
            mock_buffer.flush.return_value = {"flushed": 0, "stuck_finalized": 0}
            mock_buffer_cls.return_value = mock_buffer

            task_flush_execution_logs.run()

        mock_buffer.flush.assert_called_once_with(do_stuck_sweep=False)

    def test_task_swallows_buffer_exceptions(self):
        with patch(
            "retail.agents.tasks.ExecutionBufferService"
        ) as mock_buffer_cls, patch(
            "retail.agents.tasks._next_flush_tick", return_value=1
        ):
            mock_buffer = MagicMock()
            mock_buffer.flush.side_effect = RuntimeError("boom")
            mock_buffer_cls.return_value = mock_buffer

            result = task_flush_execution_logs.run()

        self.assertEqual(result, {"flushed": 0, "stuck_finalized": 0})


class FlushTickCounterTests(TestCase):
    """The Redis-backed tick counter used by the flush task."""

    def test_next_flush_tick_uses_redis_incr(self):
        from retail.agents.tasks import _next_flush_tick

        fake_redis = FakeRedisConnection()
        with patch("retail.agents.tasks.get_redis_connection", return_value=fake_redis):
            self.assertEqual(_next_flush_tick(), 1)
            self.assertEqual(_next_flush_tick(), 2)
            self.assertEqual(_next_flush_tick(), 3)

        # The shared counter key is the one ops can inspect for tick rate.
        self.assertEqual(fake_redis.strings.get(_FLUSH_TICK_KEY), b"3")

    def test_next_flush_tick_returns_zero_when_redis_fails(self):
        from retail.agents.tasks import _next_flush_tick

        with patch(
            "retail.agents.tasks.get_redis_connection",
            side_effect=RuntimeError("redis down"),
        ):
            self.assertEqual(_next_flush_tick(), 0)


@override_settings(
    EXECUTION_TRACES_BUCKET="test-traces-bucket",
    AGENT_EXECUTION_MAX_WAIT_SECONDS=600,
    AGENT_EXECUTION_STUCK_THRESHOLD_SECONDS=600,
)
class FlushBufferIntegrationTests(TestCase):
    """End-to-end behaviour of ``ExecutionBufferService.flush`` against
    the in-memory Redis fake and the real ``AgentExecution`` model."""

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

    def test_flush_finalises_deadline_expired_rows_as_timed_out(self):
        """A non-terminal entry past its deadline is force-finalised as error."""
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={"k": "v"},
        )
        # Force the deadline into the past
        self.fake_redis.zadd(
            self.buffer.FLUSH_QUEUE_KEY,
            {str(execution_uuid): timezone.now().timestamp() - 1},
        )

        result = self.buffer.flush()

        self.assertEqual(result["flushed"], 1)
        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.status, AgentExecutionStatus.ERROR)
        self.assertEqual(row.error_message, "Execution timed out")

    def test_flush_does_not_overwrite_a_concurrent_terminal(self):
        """A late terminal arriving between ZRANGEBYSCORE and the
        timeout UPDATE must not be flipped to ``error``.

        We simulate this by setting the row to ``success`` after the
        flush has read the entry from the queue but before the UPDATE
        runs. The ``status='processing'`` filter on the timeout UPDATE
        protects the row.
        """
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        # Pretend the deadline expired with no terminal status in Redis
        self.fake_redis.zadd(
            self.buffer.FLUSH_QUEUE_KEY,
            {str(execution_uuid): timezone.now().timestamp() - 1},
        )
        # And meanwhile the row was already moved to success out-of-band
        AgentExecution.objects.filter(uuid=execution_uuid).update(
            status=AgentExecutionStatus.SUCCESS
        )

        self.buffer.flush()

        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.status, AgentExecutionStatus.SUCCESS)

    def test_flush_writes_traces_to_s3_in_parallel(self):
        """Multiple ready entries cause one S3 PUT per execution."""
        uuids = []
        for _ in range(5):
            execution_uuid = self.buffer.start_execution(
                integrated_agent_uuid=None,
                contact_urn="unknown",
                webhook_payload={"k": "v"},
            )
            self.buffer.update_status(
                execution_uuid=execution_uuid,
                status=AgentExecutionStatus.SUCCESS,
            )
            uuids.append(execution_uuid)

        result = self.buffer.flush()

        self.assertEqual(result["flushed"], 5)
        self.assertEqual(len(self.fake_s3.put_calls), 5)
        put_keys = {call["key"] for call in self.fake_s3.put_calls}
        self.assertEqual(
            put_keys,
            {self.traces_storage.get_traces_key(u) for u in uuids},
        )

    def test_flush_handles_missing_redis_hash_gracefully(self):
        """A queue entry whose hash was evicted still gets finalised.

        Without a hash the entry is treated as non-terminal, so the
        timeout path runs: a single SQL UPDATE flips the row to
        ``error='Execution timed out'`` if it's still processing.
        """
        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=None,
            contact_urn="unknown",
            webhook_payload={},
        )
        # Force an immediate flush by setting deadline to the past
        self.fake_redis.zadd(
            self.buffer.FLUSH_QUEUE_KEY,
            {str(execution_uuid): timezone.now().timestamp() - 1},
        )
        # Simulate Redis eviction of the data hash
        del self.fake_redis.hashes[self._data_key(execution_uuid)]

        result = self.buffer.flush()

        self.assertEqual(result["flushed"], 1)
        row = AgentExecution.objects.get(uuid=execution_uuid)
        self.assertEqual(row.status, AgentExecutionStatus.ERROR)
        self.assertEqual(row.error_message, "Execution timed out")


@override_settings(
    EXECUTION_TRACES_BUCKET="test-traces-bucket",
    AGENT_EXECUTION_STUCK_THRESHOLD_SECONDS=600,
)
class StuckSweepTests(TestCase):
    """The SQL sweep that catches rows still processing past the threshold."""

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

    def _make_stuck_row(self, age_seconds: int) -> UUID:
        """Insert a processing row whose ``updated_on`` is in the past."""
        execution = AgentExecution.objects.create(
            uuid=uuid4(),
            contact_urn="unknown",
            status=AgentExecutionStatus.PROCESSING,
            traces_s3_key=f"executions/{uuid4()}/traces.json",
        )
        # auto_now=True ignores updates passed to .save(), so we go via
        # an explicit .update() to backdate the timestamp.
        AgentExecution.objects.filter(uuid=execution.uuid).update(
            updated_on=timezone.now() - timedelta(seconds=age_seconds)
        )
        return execution.uuid

    def test_sweep_finalises_old_processing_rows(self):
        stuck_uuid = self._make_stuck_row(age_seconds=601)
        fresh_uuid = self._make_stuck_row(age_seconds=10)

        result = self.buffer.flush(do_stuck_sweep=True)

        self.assertEqual(result["stuck_finalized"], 1)
        stuck = AgentExecution.objects.get(uuid=stuck_uuid)
        fresh = AgentExecution.objects.get(uuid=fresh_uuid)
        self.assertEqual(stuck.status, AgentExecutionStatus.ERROR)
        self.assertEqual(stuck.error_message, "Execution timed out")
        self.assertEqual(fresh.status, AgentExecutionStatus.PROCESSING)

    def test_sweep_with_no_stuck_rows_returns_zero(self):
        result = self.buffer.flush(do_stuck_sweep=True)
        self.assertEqual(result, {"flushed": 0, "stuck_finalized": 0})

    def test_sweep_uploads_leftover_traces_to_s3_best_effort(self):
        stuck_uuid = self._make_stuck_row(age_seconds=601)
        # Simulate leftover traces in Redis with no queue entry
        self.fake_redis.lists[f"{self.buffer.TRACES_KEY_PREFIX}{stuck_uuid}"] = [
            b'{"type":"webhook_received","timestamp":"2026-04-30","data":{}}'
        ]

        result = self.buffer.flush(do_stuck_sweep=True)

        self.assertEqual(result["stuck_finalized"], 1)
        self.assertEqual(len(self.fake_s3.put_calls), 1)


class BeatScheduleTests(TestCase):
    """Sanity checks on the celery beat configuration."""

    def test_beat_schedule_has_a_single_flush_entry(self):
        flush_entries = [
            name
            for name in settings.CELERY_BEAT_SCHEDULE
            if name.startswith("task-flush-execution-logs")
        ]
        self.assertEqual(flush_entries, ["task-flush-execution-logs"])

    def test_beat_schedule_has_no_watchdog_entries(self):
        self.assertNotIn(
            "task-watchdog-stuck-executions", settings.CELERY_BEAT_SCHEDULE
        )
        watchdog_entries = [
            name for name in settings.CELERY_BEAT_SCHEDULE if "watchdog" in name
        ]
        self.assertEqual(watchdog_entries, [])

    def test_beat_schedule_keeps_cleanup_old_executions(self):
        self.assertIn("task-cleanup-old-executions", settings.CELERY_BEAT_SCHEDULE)

    def test_settings_expose_new_buffer_knobs(self):
        self.assertTrue(hasattr(settings, "AGENT_EXECUTION_FLUSH_BATCH_SIZE"))
        self.assertTrue(hasattr(settings, "AGENT_EXECUTION_FLUSH_INTERVAL_SECONDS"))
        self.assertTrue(hasattr(settings, "AGENT_EXECUTION_MAX_WAIT_SECONDS"))
        self.assertTrue(hasattr(settings, "AGENT_EXECUTION_STUCK_SWEEP_EVERY_N_TICKS"))
        self.assertTrue(hasattr(settings, "AGENT_EXECUTION_STUCK_THRESHOLD_SECONDS"))
        self.assertTrue(hasattr(settings, "AGENT_EXECUTION_S3_PARALLEL_PUTS"))

    def test_settings_drop_old_sharding_knobs(self):
        for removed in (
            "AGENT_EXECUTION_PENDING_SHARD_COUNT",
            "AGENT_EXECUTION_PENDING_STREAM_MAXLEN",
            "AGENT_EXECUTION_PENDING_STREAM_HIGH_WATERMARK",
            "AGENT_EXECUTION_PENDING_CLAIM_IDLE_MS",
            "AGENT_EXECUTION_FLUSH_LOCK_SECONDS",
            "AGENT_EXECUTION_MAX_DELIVERY_COUNT",
            "AGENT_EXECUTION_STALE_THRESHOLD_SECONDS",
            "AGENT_EXECUTION_WATCHDOG_INTERVAL_SECONDS",
            "AGENT_EXECUTION_WATCHDOG_BATCH_SIZE",
            "AGENT_EXECUTION_WATCHDOG_LOCK_SECONDS",
        ):
            self.assertFalse(
                hasattr(settings, removed),
                f"settings.{removed} should be gone after the buffer simplification",
            )
