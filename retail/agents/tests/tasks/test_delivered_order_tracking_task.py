"""Tests for ``task_delivered_order_tracking_webhook``.

The task wraps its body in ``execution_log_scope`` for uniform error
handling. It does NOT open an ``AgentExecution`` row (no
``log_webhook_received``), so the scope only guarantees that any
failure is swallowed and logged without crashing the worker.
"""

from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.agents.domains.agent_execution.context import clear_execution_context
from retail.agents.tasks import task_delivered_order_tracking_webhook


class TaskDeliveredOrderTrackingWebhookTest(TestCase):
    def setUp(self):
        super().setUp()
        clear_execution_context()
        self.addCleanup(clear_execution_context)
        self.agent_uuid = str(uuid4())
        self.webhook_data = {
            "OrderId": "v1234567-01",
            "State": "delivered",
        }

    @patch("retail.agents.tasks.DeliveredOrderTrackingWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_task_processes_webhook_successfully(
        self, mock_logger_factory, mock_usecase_cls
    ):
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_agent = MagicMock()
        mock_usecase.get_integrated_agent.return_value = mock_agent
        mock_usecase.process_webhook_notification.return_value = {"status": "success"}

        task_delivered_order_tracking_webhook(self.agent_uuid, self.webhook_data)

        mock_usecase.get_integrated_agent.assert_called_once_with(self.agent_uuid)
        mock_usecase.process_webhook_notification.assert_called_once_with(
            mock_agent, self.webhook_data
        )
        mock_logger.log_execution_error.assert_not_called()

    @patch("retail.agents.tasks.DeliveredOrderTrackingWebhookUseCase")
    @patch("retail.agents.domains.agent_execution.task_helpers.ExecutionLoggerService")
    def test_task_swallows_processing_exception(
        self, mock_logger_factory, mock_usecase_cls
    ):
        """A failure inside processing must be swallowed by the scope so
        the worker never crashes. No execution row is opened, so nothing
        is logged against one."""
        mock_logger = MagicMock()
        mock_logger_factory.return_value = mock_logger

        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_agent = MagicMock()
        mock_usecase.get_integrated_agent.return_value = mock_agent
        mock_usecase.process_webhook_notification.side_effect = Exception(
            "Processing error"
        )

        # Must not raise.
        task_delivered_order_tracking_webhook(self.agent_uuid, self.webhook_data)

        mock_usecase.process_webhook_notification.assert_called_once_with(
            mock_agent, self.webhook_data
        )
        mock_logger.log_execution_error.assert_not_called()
