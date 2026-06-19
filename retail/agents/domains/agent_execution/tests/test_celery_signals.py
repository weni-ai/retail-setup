"""Celery worker boundary tests for the execution contextvar.

Celery prefork workers reuse processes across tasks. The execution
UUID lives in a contextvar, so without explicit cleanup, a task that
forgot to call `log_webhook_received` would inherit the previous
task's UUID and write traces to the wrong execution. The signal
handlers exercised here clear the contextvar before and after every
task, so each task starts and ends with a clean slate.
"""

from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    get_current_execution_uuid,
    set_current_execution_uuid,
)


class CeleryTaskBoundaryContextTests(TestCase):
    def tearDown(self):
        clear_execution_context()
        super().tearDown()

    def test_reset_execution_context_clears_context(self):
        from retail.celery import _reset_execution_context

        set_current_execution_uuid(uuid4())
        self.assertIsNotNone(get_current_execution_uuid())

        _reset_execution_context()

        self.assertIsNone(get_current_execution_uuid())

    def test_handler_is_connected_to_both_celery_signals(self):
        from celery.signals import task_postrun, task_prerun

        from retail.celery import _reset_execution_context

        prerun_receivers = [r() for _, r in task_prerun.receivers]
        postrun_receivers = [r() for _, r in task_postrun.receivers]

        self.assertIn(_reset_execution_context, prerun_receivers)
        self.assertIn(_reset_execution_context, postrun_receivers)
