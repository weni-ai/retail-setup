"""Tests for the AgentExecution retention sweep.

The DB cannot grow unbounded at the volume this service handles
(thousands of executions per minute), so a periodic Celery task
delegates to ``CleanupOldExecutionsUseCase`` to delete rows older
than ``AGENT_EXECUTION_RETENTION_DAYS``. The use case owns the
business logic; the task is thin glue.
"""

from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone

from retail.agents.domains.agent_execution.models import AgentExecution
from retail.agents.domains.agent_execution.usecases.cleanup_old_executions import (
    CleanupOldExecutionsUseCase,
)


def _make_execution(*, days_old: int) -> AgentExecution:
    """Create an AgentExecution and back-date its ``created_on``.

    ``auto_now_add`` blocks setting ``created_on`` on creation, so we
    UPDATE the row after insert to simulate aging.
    """
    execution = AgentExecution.objects.create(
        uuid=uuid4(),
        contact_urn="whatsapp:+5511999999999",
        status="success",
    )
    AgentExecution.objects.filter(uuid=execution.uuid).update(
        created_on=timezone.now() - timedelta(days=days_old)
    )
    execution.refresh_from_db()
    return execution


@override_settings(AGENT_EXECUTION_RETENTION_DAYS=30)
class CleanupOldExecutionsUseCaseTests(TestCase):
    def test_deletes_only_rows_older_than_retention(self):
        old = _make_execution(days_old=45)
        edge_old = _make_execution(days_old=31)
        recent = _make_execution(days_old=5)
        brand_new = _make_execution(days_old=0)

        deleted = CleanupOldExecutionsUseCase().execute()

        self.assertEqual(deleted, 2)
        self.assertFalse(AgentExecution.objects.filter(uuid=old.uuid).exists())
        self.assertFalse(AgentExecution.objects.filter(uuid=edge_old.uuid).exists())
        self.assertTrue(AgentExecution.objects.filter(uuid=recent.uuid).exists())
        self.assertTrue(AgentExecution.objects.filter(uuid=brand_new.uuid).exists())

    def test_returns_zero_when_nothing_to_delete(self):
        _make_execution(days_old=2)
        _make_execution(days_old=10)

        deleted = CleanupOldExecutionsUseCase().execute()

        self.assertEqual(deleted, 0)
        self.assertEqual(AgentExecution.objects.count(), 2)

    @override_settings(AGENT_EXECUTION_RETENTION_DAYS=7)
    def test_uses_settings_for_default_retention(self):
        too_old = _make_execution(days_old=10)
        kept = _make_execution(days_old=3)

        deleted = CleanupOldExecutionsUseCase().execute()

        self.assertEqual(deleted, 1)
        self.assertFalse(AgentExecution.objects.filter(uuid=too_old.uuid).exists())
        self.assertTrue(AgentExecution.objects.filter(uuid=kept.uuid).exists())

    def test_explicit_retention_override_takes_precedence_over_settings(self):
        """An explicit ``retention_days`` argument bypasses the setting."""
        too_old_for_explicit = _make_execution(days_old=2)
        kept = _make_execution(days_old=0)

        deleted = CleanupOldExecutionsUseCase().execute(retention_days=1)

        self.assertEqual(deleted, 1)
        self.assertFalse(
            AgentExecution.objects.filter(uuid=too_old_for_explicit.uuid).exists()
        )
        self.assertTrue(AgentExecution.objects.filter(uuid=kept.uuid).exists())

    def test_logs_count_when_rows_are_deleted(self):
        """The sweep emits a single INFO line with the deleted count
        and the retention window — SRE relies on that log to alert on
        "cleanup ran but deleted zero" vs "cleanup ran and trimmed the
        expected volume". The zero-deleted case stays silent on
        purpose so the alert does not spam.
        """
        _make_execution(days_old=45)
        _make_execution(days_old=31)
        _make_execution(days_old=1)

        with self.assertLogs(
            "retail.agents.domains.agent_execution.usecases.cleanup_old_executions",
            level="INFO",
        ) as captured:
            deleted = CleanupOldExecutionsUseCase().execute()

        self.assertEqual(deleted, 2)
        self.assertEqual(len(captured.records), 1)
        message = captured.records[0].getMessage()
        self.assertIn("[EXEC_LOG]", message)
        self.assertIn("Cleaned up 2 agent executions", message)
        self.assertIn("30 days", message)

    def test_no_log_when_nothing_to_delete(self):
        """Zero-deleted runs stay silent so the INFO log stream is a
        clean signal of actual retention activity.
        """
        _make_execution(days_old=5)

        logger_name = (
            "retail.agents.domains.agent_execution.usecases.cleanup_old_executions"
        )
        with self.assertNoLogs(logger_name, level="INFO"):
            deleted = CleanupOldExecutionsUseCase().execute()

        self.assertEqual(deleted, 0)

    @override_settings(AGENT_EXECUTION_CLEANUP_BATCH_SIZE=5)
    def test_batched_delete_handles_more_rows_than_batch_size(self):
        """The sweep loops until no expired rows remain. Each batch
        is bounded by ``AGENT_EXECUTION_CLEANUP_BATCH_SIZE`` so a
        single ``DELETE`` never holds row locks across the full
        retention horizon; the return value is the total across
        batches and the INFO log fires once with that total.
        """
        for _ in range(12):
            _make_execution(days_old=45)
        kept = _make_execution(days_old=5)

        logger_name = (
            "retail.agents.domains.agent_execution.usecases.cleanup_old_executions"
        )
        with self.assertLogs(logger_name, level="INFO") as captured:
            deleted = CleanupOldExecutionsUseCase().execute()

        self.assertEqual(deleted, 12)
        self.assertEqual(AgentExecution.objects.count(), 1)
        self.assertTrue(AgentExecution.objects.filter(uuid=kept.uuid).exists())
        self.assertEqual(len(captured.records), 1)
        self.assertIn(
            "Cleaned up 12 agent executions", captured.records[0].getMessage()
        )

    @override_settings(AGENT_EXECUTION_CLEANUP_BATCH_SIZE=5)
    def test_batch_loop_terminates_on_empty_set(self):
        """An empty initial batch breaks the loop without ever
        issuing a DELETE — preserves the silent zero-deleted contract
        even when batching is enabled.
        """
        _make_execution(days_old=2)

        logger_name = (
            "retail.agents.domains.agent_execution.usecases.cleanup_old_executions"
        )
        with self.assertNoLogs(logger_name, level="INFO"):
            deleted = CleanupOldExecutionsUseCase().execute()

        self.assertEqual(deleted, 0)
        self.assertEqual(AgentExecution.objects.count(), 1)


class TaskCleanupOldExecutionsTests(TestCase):
    """The Celery task is just glue: delegate to the use case and
    swallow exceptions so the beat schedule keeps trying.
    """

    @patch(
        "retail.agents.tasks.CleanupOldExecutionsUseCase",
    )
    def test_task_returns_use_case_result(self, mock_use_case_cls):
        from retail.agents.tasks import task_cleanup_old_executions

        mock_use_case_cls.return_value.execute.return_value = 7

        self.assertEqual(task_cleanup_old_executions(), 7)
        mock_use_case_cls.return_value.execute.assert_called_once_with()

    @patch(
        "retail.agents.tasks.CleanupOldExecutionsUseCase",
    )
    def test_task_swallows_exception_and_returns_zero(self, mock_use_case_cls):
        from retail.agents.tasks import task_cleanup_old_executions

        mock_use_case_cls.return_value.execute.side_effect = RuntimeError("boom")

        self.assertEqual(task_cleanup_old_executions(), 0)
