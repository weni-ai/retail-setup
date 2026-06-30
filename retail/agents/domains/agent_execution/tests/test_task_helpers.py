"""Tests for ``execution_log_scope`` and terminal error logging."""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from celery.exceptions import Retry
from django.test import TestCase

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    set_current_execution_uuid,
)
from retail.agents.domains.agent_execution.task_helpers import execution_log_scope


class ExecutionLogScopeTest(TestCase):
    def setUp(self):
        clear_execution_context()
        self.addCleanup(clear_execution_context)

    @patch("retail.agents.domains.agent_execution.task_helpers.logger")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_reraises_retry_after_logging(self, mock_factory, mock_logger):
        mock_factory.return_value = MagicMock()

        with self.assertRaises(Retry):
            with execution_log_scope(log_prefix="[TASK]"):
                raise Retry()

        mock_logger.error.assert_called_once()

    @patch("retail.agents.domains.agent_execution.task_helpers.logger")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_reraises_retry_with_sentry_tags(self, mock_factory, mock_logger):
        mock_factory.return_value = MagicMock()
        sentry_tags = {"vtex_account": "store", "project_uuid": "p-1"}

        with self.assertRaises(Retry):
            with execution_log_scope(
                log_prefix="[CART_TASK]",
                sentry_tags=sentry_tags,
                sentry_fingerprint=["cart-task", "Retry"],
            ):
                raise Retry()

        mock_logger.error.assert_called_once()
        self.assertIn("[CART_TASK] task_failed", mock_logger.error.call_args[0][0])

    @patch("retail.agents.domains.agent_execution.task_helpers.logger")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_suppressed_exception_logs_execution_error(self, mock_factory, mock_logger):
        execution_uuid = uuid4()
        mock_exec = MagicMock()
        mock_factory.return_value = mock_exec

        with execution_log_scope(error_data={"key": "value"}, log_prefix="[TASK]"):
            set_current_execution_uuid(execution_uuid)
            raise RuntimeError("boom")

        mock_exec.log_execution_error.assert_called_once_with(
            execution_uuid=execution_uuid,
            error_message="boom",
            error_data={"key": "value"},
        )
        mock_logger.error.assert_called_once()

    @patch("retail.agents.domains.agent_execution.task_helpers.logger")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_error_data_factory_failure_continues_with_partial_data(
        self, mock_factory, mock_logger
    ):
        execution_uuid = uuid4()
        mock_exec = MagicMock()
        mock_factory.return_value = mock_exec

        def failing_factory():
            raise ValueError("factory broken")

        with execution_log_scope(
            error_data={"static": True},
            error_data_factory=failing_factory,
            log_prefix="[TASK]",
        ):
            set_current_execution_uuid(execution_uuid)
            raise RuntimeError("task failed")

        mock_exec.log_execution_error.assert_called_once()
        kwargs = mock_exec.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs["error_data"], {"static": True})
        mock_logger.exception.assert_called_once()
