"""Tests for ``DeliveredOrderTrackingWebhookView``."""

from unittest.mock import patch
from uuid import uuid4

from django.urls import reverse
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.test import APITestCase


class DeliveredOrderTrackingWebhookViewTest(APITestCase):
    def setUp(self):
        self.agent_uuid = uuid4()
        self.url = reverse(
            "delivered-order-tracking-webhook",
            kwargs={"pk": self.agent_uuid},
        )
        self.webhook_payload = {
            "OrderId": "v1234567-01",
            "State": "delivered",
        }

    @patch(
        "retail.agents.domains.agent_integration.views.task_delivered_order_tracking_webhook"
    )
    @patch(
        "retail.agents.domains.agent_integration.views.DeliveredOrderTrackingWebhookUseCase"
    )
    def test_post_schedules_task_for_active_agent(self, mock_usecase_cls, mock_task):
        mock_usecase = mock_usecase_cls.return_value
        mock_usecase.get_integrated_agent.return_value = object()

        response = self.client.post(self.url, self.webhook_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_usecase.get_integrated_agent.assert_called_once_with(str(self.agent_uuid))
        mock_task.apply_async.assert_called_once_with(
            args=[self.agent_uuid, self.webhook_payload],
            queue="vtex-io-orders-update-events",
        )

    @patch(
        "retail.agents.domains.agent_integration.views.task_delivered_order_tracking_webhook"
    )
    @patch(
        "retail.agents.domains.agent_integration.views.DeliveredOrderTrackingWebhookUseCase"
    )
    def test_post_skips_task_when_agent_is_inactive(self, mock_usecase_cls, mock_task):
        mock_usecase = mock_usecase_cls.return_value
        mock_usecase.get_integrated_agent.side_effect = NotFound()

        response = self.client.post(self.url, self.webhook_payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["message"], "Webhook received")
        mock_task.apply_async.assert_not_called()
