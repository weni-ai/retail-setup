from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.agents.tasks import task_payment_recovery_webhook


class TaskPaymentRecoveryWebhookTest(TestCase):
    def setUp(self):
        self.agent_uuid = str(uuid4())
        self.webhook_data = {
            "OrderId": "v1234567-01",
            "State": "payment-pending",
        }

    @patch("retail.agents.tasks.PaymentRecoveryWebhookUseCase")
    def test_task_processes_webhook_successfully(self, mock_usecase_cls):
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

    @patch("retail.agents.tasks.PaymentRecoveryWebhookUseCase")
    def test_task_handles_exception_gracefully(self, mock_usecase_cls):
        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_usecase.get_integrated_agent.side_effect = Exception("Agent not found")

        task_payment_recovery_webhook(self.agent_uuid, self.webhook_data)

    @patch("retail.agents.tasks.PaymentRecoveryWebhookUseCase")
    def test_task_handles_process_exception_gracefully(self, mock_usecase_cls):
        mock_usecase = MagicMock()
        mock_usecase_cls.return_value = mock_usecase
        mock_agent = MagicMock()
        mock_usecase.get_integrated_agent.return_value = mock_agent
        mock_usecase.process_webhook_notification.side_effect = Exception(
            "Processing error"
        )

        task_payment_recovery_webhook(self.agent_uuid, self.webhook_data)
