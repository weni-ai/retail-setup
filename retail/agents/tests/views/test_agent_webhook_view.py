"""Tests for `AgentWebhookView`.

The view is a thin entrypoint that hands the inbound webhook off to a
Celery task. It must:

- Return 200 with `{"message": "Webhook received"}` for every call.
- Stamp `Origin = {"Sender": "agent-webhook"}` into the payload before
  scheduling the task.
- Skip scheduling entirely when the webhook UUID matches the
  `IGNORE_AGENT_UUID` sentinel.
- Schedule on the `vtex-io-orders-update-events` queue.
- Be reachable by anonymous clients (AllowAny).
"""

from uuid import uuid4
from unittest.mock import patch
from urllib.parse import urlencode

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from django.urls import reverse

from retail.agents.domains.agent_webhook.views import AgentWebhookView


TASK_PATH = "retail.agents.domains.agent_webhook.views.task_agent_webhook"


class AgentWebhookViewTest(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.webhook_uuid = uuid4()
        self.url = reverse("agent-webhook", kwargs={"webhook_uuid": self.webhook_uuid})

    @patch(TASK_PATH)
    def test_post_returns_200_and_schedules_task(self, mock_task):
        payload = {"orderId": "ORD-1", "status": "invoiced"}

        response = self.client.post(self.url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "Webhook received"})
        mock_task.apply_async.assert_called_once()

    @patch(TASK_PATH)
    def test_post_stamps_origin_and_forwards_payload(self, mock_task):
        payload = {"orderId": "ORD-1", "status": "invoiced"}

        self.client.post(self.url, data=payload, format="json")

        _, call_kwargs = mock_task.apply_async.call_args
        args = call_kwargs["args"]
        self.assertEqual(call_kwargs["queue"], "vtex-io-orders-update-events")
        self.assertEqual(args[0], str(self.webhook_uuid))

        forwarded_payload = args[1]
        self.assertEqual(forwarded_payload["orderId"], "ORD-1")
        self.assertEqual(forwarded_payload["status"], "invoiced")
        self.assertEqual(forwarded_payload["Origin"], {"Sender": "agent-webhook"})

    @patch(TASK_PATH)
    def test_post_forwards_query_params(self, mock_task):
        params = {"an": "myaccount", "wf": "1"}
        full_url = f"{self.url}?{urlencode(params)}"

        self.client.post(full_url, data={}, format="json")

        _, call_kwargs = mock_task.apply_async.call_args
        args = call_kwargs["args"]
        forwarded_params = args[2]

        self.assertIsInstance(forwarded_params, dict)
        self.assertIn("an", forwarded_params)
        self.assertIn("wf", forwarded_params)
        self.assertIn("myaccount", str(forwarded_params["an"]))
        self.assertIn("1", str(forwarded_params["wf"]))

    @patch(TASK_PATH)
    def test_post_ignores_blocked_uuid(self, mock_task):
        blocked_url = reverse(
            "agent-webhook",
            kwargs={"webhook_uuid": AgentWebhookView.IGNORE_AGENT_UUID},
        )

        response = self.client.post(
            blocked_url, data={"orderId": "ORD-1"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "Webhook received"})
        mock_task.apply_async.assert_not_called()

    @patch(TASK_PATH)
    def test_post_does_not_mutate_request_payload_origin(self, mock_task):
        payload = {"orderId": "ORD-1", "Origin": {"Sender": "vtex"}}

        self.client.post(self.url, data=payload, format="json")

        _, call_kwargs = mock_task.apply_async.call_args
        forwarded_payload = call_kwargs["args"][1]
        self.assertEqual(forwarded_payload["Origin"], {"Sender": "agent-webhook"})

    @patch(TASK_PATH)
    def test_post_allows_anonymous_client(self, mock_task):
        self.client.force_authenticate(user=None)

        response = self.client.post(self.url, data={}, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_task.apply_async.assert_called_once()

    def test_view_uses_allow_any_permission(self):
        from rest_framework.permissions import AllowAny

        self.assertEqual(AgentWebhookView.permission_classes, [AllowAny])
