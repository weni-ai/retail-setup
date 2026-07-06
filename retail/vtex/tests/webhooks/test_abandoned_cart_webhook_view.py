"""Tests for `AbandonedCartWebhookView`."""

from uuid import uuid4
from unittest.mock import Mock, patch
from urllib.parse import urlencode

from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project


RESOLVER_PATH = (
    "retail.webhooks.vtex.views.abandoned_cart_webhook."
    "IntegratedAgentWebhookResolver"
)
PROCESS_CART_PATH = (
    "retail.webhooks.vtex.views.abandoned_cart_webhook."
    "ProcessAbandonedCartNotificationUseCase"
)
ABANDONED_CART_AGENT_UUID = str(uuid4())


class AbandonedCartWebhookViewTest(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.integrated_agent_uuid = uuid4()
        self.url = reverse(
            "abandoned-cart-webhook",
            kwargs={"pk": self.integrated_agent_uuid},
        )

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    @override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
    def test_post_processes_abandoned_cart_notification(
        self, mock_resolver_cls, mock_process_cart_cls
    ):
        integrated_agent = Mock()
        integrated_agent.uuid = self.integrated_agent_uuid
        mock_resolver_cls.return_value.resolve.return_value = integrated_agent
        mock_process_cart_instance = Mock()
        mock_process_cart_cls.from_integrated_agent.return_value = (
            mock_process_cart_instance
        )

        payload = {
            "order_form_id": "order-123",
            "phone": "5584987654321",
            "name": "Test User",
        }
        response = self.client.post(self.url, data=payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "Webhook received"})
        mock_process_cart_cls.from_integrated_agent.assert_called_once_with(
            integrated_agent
        )
        mock_process_cart_instance.execute.assert_called_once()

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    @override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
    def test_post_accepts_query_params_only(
        self, mock_resolver_cls, mock_process_cart_cls
    ):
        integrated_agent = Mock()
        mock_resolver_cls.return_value.resolve.return_value = integrated_agent
        mock_process_cart_instance = Mock()
        mock_process_cart_cls.from_integrated_agent.return_value = (
            mock_process_cart_instance
        )

        query = urlencode(
            {
                "order_form_id": "order-123",
                "phone": "5584987654321",
                "name": "Test User",
            }
        )
        response = self.client.post(f"{self.url}?{query}")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_process_cart_instance.execute.assert_called_once()

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    @override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
    def test_post_body_takes_precedence_over_query_params(
        self, mock_resolver_cls, mock_process_cart_cls
    ):
        integrated_agent = Mock()
        mock_resolver_cls.return_value.resolve.return_value = integrated_agent
        mock_process_cart_instance = Mock()
        mock_process_cart_cls.from_integrated_agent.return_value = (
            mock_process_cart_instance
        )

        query = urlencode(
            {
                "order_form_id": "query-order",
                "phone": "5511000000000",
                "name": "Query User",
            }
        )
        response = self.client.post(
            f"{self.url}?{query}",
            data={
                "order_form_id": "body-order",
                "phone": "5584987654321",
                "name": "Body User",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dto = mock_process_cart_instance.execute.call_args[0][0]
        self.assertEqual(dto.order_form_id, "body-order")
        self.assertEqual(dto.phone, "5584987654321")
        self.assertEqual(dto.name, "Body User")

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    @override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
    def test_post_merges_query_params_and_body_fields(
        self, mock_resolver_cls, mock_process_cart_cls
    ):
        integrated_agent = Mock()
        mock_resolver_cls.return_value.resolve.return_value = integrated_agent
        mock_process_cart_instance = Mock()
        mock_process_cart_cls.from_integrated_agent.return_value = (
            mock_process_cart_instance
        )

        query = urlencode(
            {
                "order_form_id": "order-123",
                "phone": "5584987654321",
            }
        )
        response = self.client.post(
            f"{self.url}?{query}",
            data={"name": "Test User"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        dto = mock_process_cart_instance.execute.call_args[0][0]
        self.assertEqual(dto.order_form_id, "order-123")
        self.assertEqual(dto.phone, "5584987654321")
        self.assertEqual(dto.name, "Test User")

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    @override_settings(ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID)
    def test_post_errors_still_return_200(
        self, mock_resolver_cls, mock_process_cart_cls
    ):
        integrated_agent = Mock()
        mock_resolver_cls.return_value.resolve.return_value = integrated_agent
        mock_process_cart_instance = Mock()
        mock_process_cart_instance.execute.side_effect = ValueError("boom")
        mock_process_cart_cls.from_integrated_agent.return_value = (
            mock_process_cart_instance
        )

        response = self.client.post(
            self.url,
            data={
                "order_form_id": "order-123",
                "phone": "5584987654321",
                "name": "Test",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "Webhook received"})

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    def test_post_ping_via_query_params_skips_processing(
        self, mock_resolver_cls, mock_process_cart_cls
    ):
        response = self.client.post(f"{self.url}?hookConfig=ping")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_resolver_cls.assert_not_called()
        mock_process_cart_cls.assert_not_called()

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    def test_post_ping_skips_processing(self, mock_resolver_cls, mock_process_cart_cls):
        response = self.client.post(
            self.url, data={"hookConfig": "ping"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_resolver_cls.assert_not_called()
        mock_process_cart_cls.assert_not_called()

    @patch(PROCESS_CART_PATH)
    @patch(RESOLVER_PATH)
    def test_post_missing_agent_still_returns_200(
        self, mock_resolver_cls, mock_process_cart_cls
    ):
        mock_resolver_cls.return_value.resolve.return_value = None

        response = self.client.post(
            self.url,
            data={
                "order_form_id": "order-123",
                "phone": "5584987654321",
                "name": "Test",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_process_cart_cls.assert_not_called()


class FakeRedisLock:
    def __init__(self):
        self.store = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    def delete(self, key):
        self.store.pop(key, None)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "abandoned-cart-webhook-integration-tests",
        }
    },
    ABANDONED_CART_AGENT_UUID=ABANDONED_CART_AGENT_UUID,
)
class AbandonedCartWebhookIntegrationTest(APITestCase):
    def setUp(self):
        super().setUp()
        self.client = APIClient()
        self.project = Project.objects.create(uuid=uuid4(), vtex_account="test-account")
        self.agent = Agent.objects.create(
            uuid=ABANDONED_CART_AGENT_UUID,
            name="Abandoned Cart",
            slug="abandoned-cart",
            description="Abandoned cart agent",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            config={"abandoned_cart": {"abandonment_time_minutes": 30}},
        )
        self.url = reverse(
            "abandoned-cart-webhook",
            kwargs={"pk": self.integrated_agent.uuid},
        )

    @patch("retail.webhooks.vtex.usecases.cart.task_abandoned_cart_update.apply_async")
    @patch("retail.webhooks.vtex.usecases.cart.get_redis_connection")
    def test_post_runs_cart_pipeline_end_to_end(
        self, mock_get_redis_connection, mock_apply_async
    ):
        from retail.vtex.models import Cart

        mock_get_redis_connection.return_value = FakeRedisLock()

        response = self.client.post(
            self.url,
            data={
                "order_form_id": "order-123",
                "phone": "+55 (84) 98765-4321",
                "name": "Test User",
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "Webhook received"})

        cart = Cart.objects.get(
            order_form_id="order-123",
            project=self.project,
            phone_number="5584987654321",
        )
        self.assertEqual(cart.integrated_agent, self.integrated_agent)
        self.assertEqual(cart.status, "created")
        mock_apply_async.assert_called_once()

    @patch(RESOLVER_PATH)
    def test_post_invalid_payload_still_returns_200(self, mock_resolver_cls):
        integrated_agent = Mock()
        mock_resolver_cls.return_value.resolve.return_value = integrated_agent

        response = self.client.post(
            self.url, data={"order_form_id": "order-123"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {"message": "Webhook received"})
