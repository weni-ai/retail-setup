"""Tests for ``PaymentRecoveryWebhookView``."""

from unittest.mock import patch
from uuid import uuid4

from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.test import APITestCase


class PaymentRecoveryWebhookViewTest(APITestCase):
    def setUp(self):
        self.agent_uuid = uuid4()
        self.url = reverse(
            "payment-recovery-webhook",
            kwargs={"pk": self.agent_uuid},
        )
        self.webhook_payload = {
            "OrderId": "v1234567-01",
            "State": "payment-pending",
        }

    @patch(
        "retail.agents.domains.agent_integration.views.task_payment_recovery_webhook"
    )
    @patch(
        "retail.agents.domains.agent_integration.views.PaymentRecoveryWebhookUseCase"
    )
    def test_post_schedules_task_for_active_agent(self, mock_usecase_cls, mock_task):
        mock_usecase = mock_usecase_cls.return_value
        mock_usecase.get_integrated_agent.return_value = object()
        mock_usecase.get_delay_seconds.return_value = 300

        response = self.client.post(self.url, self.webhook_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_usecase.get_integrated_agent.assert_called_once_with(self.agent_uuid)
        mock_task.apply_async.assert_called_once_with(
            args=[self.agent_uuid, self.webhook_payload],
            countdown=300,
            queue="vtex-io-orders-update-events",
        )

    @patch(
        "retail.agents.domains.agent_integration.views.task_payment_recovery_webhook"
    )
    @patch(
        "retail.agents.domains.agent_integration.views.PaymentRecoveryWebhookUseCase"
    )
    def test_post_skips_task_when_agent_is_inactive(self, mock_usecase_cls, mock_task):
        mock_usecase = mock_usecase_cls.return_value
        mock_usecase.get_integrated_agent.side_effect = NotFound()

        response = self.client.post(self.url, self.webhook_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Webhook received")
        mock_task.apply_async.assert_not_called()
