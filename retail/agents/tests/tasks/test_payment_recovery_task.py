"""Tests for ``task_payment_recovery_webhook``.

The task opens an `AgentExecution` row via
``log_webhook_received`` once the integrated agent is resolved, and
must close it as ``error`` if processing raises. The agent-missing
branch must NOT open a log.
"""

from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_execution.context import clear_execution_context
from retail.agents.tasks import task_payment_recovery_webhook


class TaskPaymentRecoveryWebhookTest(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)
        self.agent_uuid = str(uuid4())
        self.webhook_data = {
            "OrderId": "v1234567-01",
            "State": "payment-pending",
        }

    @patch("retail.agents.tasks.PaymentRecoveryWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_task_processes_webhook_successfully(
        self, mock_logger_factory, mock_usecase_cls
    ):
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = uuid4()
        mock_logger_factory.return_value = mock_logger

        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_agent = MagicMock()
        mock_usecase.get_integrated_agent.return_value = mock_agent
        mock_usecase.process_webhook_notification.return_value = {"status": "success"}

        task_payment_recovery_webhook(self.agent_uuid, self.webhook_data)

        mock_usecase.get_integrated_agent.assert_called_once_with(self.agent_uuid)
        mock_usecase.process_webhook_notification.assert_called_once_with(
            mock_agent, self.webhook_data
        )
        mock_logger.log_execution_error.assert_not_called()

    @patch("retail.agents.tasks.PaymentRecoveryWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_log_webhook_received_carries_order_id_and_agent(
        self, mock_logger_factory, mock_usecase_cls
    ):
        """The open-log call must carry ``order_id`` and the
        resolved ``IntegratedAgent`` so the public agent-logs API can
        surface the order context for payment-recovery executions."""
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.return_value = uuid4()
        mock_logger_factory.return_value = mock_logger

        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_agent = MagicMock()
        mock_usecase.get_integrated_agent.return_value = mock_agent

        task_payment_recovery_webhook(self.agent_uuid, self.webhook_data)

        mock_logger.log_webhook_received.assert_called_once()
        kwargs = mock_logger.log_webhook_received.call_args.kwargs
        self.assertIs(kwargs.get("integrated_agent"), mock_agent)
        self.assertEqual(kwargs.get("payload"), self.webhook_data)
        self.assertEqual(kwargs.get("order_id"), self.webhook_data["OrderId"])

    @patch("retail.agents.tasks.PaymentRecoveryWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_task_handles_exception_gracefully(
        self, mock_logger_factory, mock_usecase_cls
    ):
        """A missing agent must not leave behind an execution
        row. ``get_integrated_agent`` raises ``NotFound``; the outer
        ``except`` swallows the error before any log is opened."""
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_usecase.get_integrated_agent.side_effect = NotFound("Inactive agent")

        # Must not raise.
        task_payment_recovery_webhook(self.agent_uuid, self.webhook_data)

        mock_logger.log_webhook_received.assert_not_called()
        mock_logger.log_execution_error.assert_not_called()
        mock_usecase.process_webhook_notification.assert_not_called()

    @patch("retail.agents.tasks.PaymentRecoveryWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_task_handles_process_exception_gracefully(
        self, mock_logger_factory, mock_usecase_cls
    ):
        """An exception inside processing must close
        the previously-opened execution row as ``error`` rather than
        leaving it to time out at the ZSET deadline."""
        from retail.agents.domains.agent_execution.context import (
            set_current_execution_uuid,
        )

        execution_uuid = uuid4()
        mock_logger = MagicMock()
        mock_logger.log_webhook_received.side_effect = lambda *a, **kw: (
            set_current_execution_uuid(execution_uuid),
            execution_uuid,
        )[1]
        mock_logger_factory.return_value = mock_logger

        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_agent = MagicMock()
        mock_usecase.get_integrated_agent.return_value = mock_agent
        mock_usecase.process_webhook_notification.side_effect = Exception(
            "Processing error"
        )

        # Must not raise.
        task_payment_recovery_webhook(self.agent_uuid, self.webhook_data)

        mock_logger.log_execution_error.assert_called_once()
        kwargs = mock_logger.log_execution_error.call_args.kwargs
        self.assertEqual(kwargs.get("execution_uuid"), execution_uuid)
        self.assertEqual(kwargs.get("error_message"), "Processing error")
        self.assertEqual(
            kwargs.get("error_data"),
            {
                "integrated_agent_uuid": self.agent_uuid,
                "webhook_data": self.webhook_data,
            },
        )
