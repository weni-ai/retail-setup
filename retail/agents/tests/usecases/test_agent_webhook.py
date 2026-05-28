from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.webhook import (
    AgentWebhookUseCase,
)
from retail.agents.tests.mocks.cache.integrated_agent_webhook import (
    IntegratedAgentCacheHandlerMock,
)
from retail.broadcasts.usecases.record_broadcast_sent import (
    BroadcastDispatchContext,
)
from retail.interfaces.clients.aws_lambda.client import RequestData


class AgentWebhookUseCaseTest(TestCase):
    """Test cases for AgentWebhookUseCase functionality."""

    def setUp(self):
        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_handler = MagicMock()
        self.mock_broadcast_handler = MagicMock()
        self.mock_cache_handler = IntegratedAgentCacheHandlerMock()

        self.usecase = AgentWebhookUseCase(
            active_agent=self.mock_lambda_handler,
            broadcast=self.mock_broadcast_handler,
            cache=self.mock_cache_handler,
        )
        self.mock_agent = MagicMock()
        self.mock_agent.uuid = uuid4()
        self.mock_agent.ignore_templates = False
        self.mock_agent.project.uuid = uuid4()
        self.mock_agent.project.vtex_account = "test_account"
        self.mock_agent.project.is_blocked = False
        self.mock_agent.agent.lambda_arn = (
            "arn:aws:lambda:region:account-id:function:function-name"
        )
        self.mock_agent.channel_uuid = uuid4()
        self.mock_agent.contact_percentage = 100
        self.mock_agent.config = None
        self.mock_agent.templates.get.return_value.current_version.template_name = (
            "template_v1"
        )
        self.mock_agent.credentials.all.return_value = []

    def test_should_send_broadcast_100_percent(self):
        self.mock_agent.contact_percentage = 100
        self.assertTrue(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_not_send_broadcast_0_percent(self):
        self.mock_agent.contact_percentage = 0
        self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_not_send_broadcast_none_percent(self):
        self.mock_agent.contact_percentage = None
        self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_not_send_broadcast_negative_percent(self):
        self.mock_agent.contact_percentage = -10
        self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_should_send_broadcast_random(self):
        self.mock_agent.contact_percentage = 50
        with patch("random.randint", return_value=25):
            self.assertTrue(self.usecase._should_send_broadcast(self.mock_agent))
        with patch("random.randint", return_value=75):
            self.assertFalse(self.usecase._should_send_broadcast(self.mock_agent))

    def test_addapt_credentials(self):
        cred1 = MagicMock()
        cred1.key = "user"
        cred1.value = "john"
        cred2 = MagicMock()
        cred2.key = "pass"
        cred2.value = "doe"
        self.mock_agent.credentials.all.return_value = [cred1, cred2]
        creds = self.usecase._addapt_credentials(self.mock_agent)
        self.assertEqual(creds, {"user": "john", "pass": "doe"})

    def test_addapt_credentials_empty(self):
        self.mock_agent.credentials.all.return_value = []
        creds = self.usecase._addapt_credentials(self.mock_agent)
        self.assertEqual(creds, {})

    def test_get_integrated_agent_blocked_uuid(self):
        blocked_uuid = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"
        result = self.usecase._get_integrated_agent(blocked_uuid)
        self.assertIsNone(result)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_get_integrated_agent_found(self, mock_get):
        mock_agent = MagicMock()
        mock_agent.project.is_blocked = False
        mock_get.return_value = mock_agent
        test_uuid = uuid4()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_get_integrated_agent_not_found(self, mock_get):
        mock_get.side_effect = IntegratedAgent.DoesNotExist()
        test_uuid = uuid4()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertIsNone(result)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)

    def test_execute_successful(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}

        result = self.usecase.execute(self.mock_agent, MagicMock())

        # On success, execute returns the Lambda response so callers (e.g. the
        # cart abandonment service) can tell that the broadcast was dispatched.
        self.assertIsNotNone(result)
        self.assertIs(result, mock_response)
        self.mock_broadcast_handler.send_message.assert_called_once()

    def test_execute_should_not_send_broadcast(self):
        self.mock_agent.contact_percentage = 0
        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_parse_response_failure_logs_vtex_account(self):
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = None

        with self.assertLogs(
            "retail.agents.domains.agent_webhook.usecases.webhook",
            level="INFO",
        ) as captured:
            result = self.usecase.execute(self.mock_agent, MagicMock())

        self.assertIsNone(result)
        self.mock_broadcast_handler.build_message.assert_not_called()
        self.assertTrue(
            any(
                "Error in parsing lambda response" in line
                and "vtex_account=test_account" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_execute_missing_template_error(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "error": "Missing template"
        }
        self.mock_lambda_handler.validate_response.return_value = False

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_template_not_active(self):
        # build_message returning None simulates the template lookup failing
        # (e.g. inactive or without an approved current_version).
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = None

        result = self.usecase.execute(self.mock_agent, MagicMock())

        self.assertIsNone(result)
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_contact_not_allowed(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = False

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_lambda_error_message(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "errorMessage": "Some error"
        }
        self.mock_lambda_handler.validate_response.return_value = False

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_template_not_found(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "not_found",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = None

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_build_message_exception(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.side_effect = Exception(
            "Build message error"
        )

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_build_message_returns_none(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = None

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_build_message_returns_empty_dict(self):
        mock_response = {"Payload": MagicMock()}
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {}

        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)
        self.mock_broadcast_handler.send_message.assert_not_called()

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_get_integrated_agent_from_cache(self, mock_get):
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid
        mock_agent.project.is_blocked = False

        self.mock_cache_handler.set_cached_agent(mock_agent)

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_not_called()

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_get_integrated_agent_cache_miss_then_set(self, mock_get):
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid
        mock_agent.project.is_blocked = False
        mock_get.return_value = mock_agent

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertEqual(cached_agent, mock_agent)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_get_integrated_agent_cache_miss_not_found(self, mock_get):
        mock_get.side_effect = IntegratedAgent.DoesNotExist()
        test_uuid = uuid4()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertIsNone(result)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertIsNone(cached_agent)

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_get_integrated_agent_cache_with_none_value(self, mock_get):
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid
        mock_agent.project.is_blocked = False
        mock_get.return_value = mock_agent

        self.mock_cache_handler.cache[str(test_uuid)] = None

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertEqual(cached_agent, mock_agent)

    def test_get_integrated_agent_blocked_uuid_no_cache_interaction(self):
        blocked_uuid = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"

        result = self.usecase._get_integrated_agent(blocked_uuid)

        self.assertIsNone(result)
        cached_agent = self.mock_cache_handler.get_cached_agent(blocked_uuid)
        self.assertIsNone(cached_agent)


class ExtractDispatchContextTest(TestCase):
    """Validates how the commercial origin is read from the request
    payload built by each upstream orchestrator.

    Two literal keys are supported, mirroring exactly what the
    callers populate today: ``order_form_id`` (cart abandonment) and
    ``OrderId`` (VTEX-shaped order-status / payment-recovery).
    """

    def test_returns_none_for_empty_payload(self):
        self.assertIsNone(AgentWebhookUseCase._extract_dispatch_context(None))
        self.assertIsNone(AgentWebhookUseCase._extract_dispatch_context({}))

    def test_returns_none_when_payload_has_no_commercial_keys(self):
        self.assertIsNone(
            AgentWebhookUseCase._extract_dispatch_context(
                {"phone_number": "5511", "client_name": "Maria"}
            )
        )

    def test_extracts_order_form_id_for_cart_flow(self):
        context = AgentWebhookUseCase._extract_dispatch_context(
            {"order_form_id": "of-cart-9", "phone_number": "5511"}
        )

        self.assertEqual(context, BroadcastDispatchContext(order_form_id="of-cart-9"))

    def test_extracts_order_id_for_order_status_flow(self):
        context = AgentWebhookUseCase._extract_dispatch_context(
            {"OrderId": "order-77", "Domain": "Marketplace"}
        )

        self.assertEqual(context, BroadcastDispatchContext(order_id="order-77"))

    def test_extracts_both_when_payload_carries_them(self):
        context = AgentWebhookUseCase._extract_dispatch_context(
            {"order_form_id": "of-1", "OrderId": "order-1"}
        )

        self.assertEqual(
            context,
            BroadcastDispatchContext(order_form_id="of-1", order_id="order-1"),
        )

    def test_skips_empty_string_values(self):
        self.assertIsNone(
            AgentWebhookUseCase._extract_dispatch_context(
                {"order_form_id": "", "OrderId": ""}
            )
        )

    def test_coerces_non_string_values_to_string(self):
        context = AgentWebhookUseCase._extract_dispatch_context({"OrderId": 123456})

        self.assertEqual(context, BroadcastDispatchContext(order_id="123456"))


class AgentWebhookExecutePropagatesContextTest(TestCase):
    """End-to-end propagation of the dispatch context through ``execute``.

    The dispatch context is captured at the orchestrator level (request
    payload), independently of what the Lambda response carries, so a
    Lambda that does not echo the order id back never breaks attribution.
    """

    def setUp(self):
        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_handler = MagicMock()
        self.mock_broadcast_handler = MagicMock()
        self.mock_cache_handler = IntegratedAgentCacheHandlerMock()

        self.usecase = AgentWebhookUseCase(
            active_agent=self.mock_lambda_handler,
            broadcast=self.mock_broadcast_handler,
            cache=self.mock_cache_handler,
        )
        self.mock_agent = MagicMock()
        self.mock_agent.uuid = uuid4()
        self.mock_agent.contact_percentage = 100
        self.mock_agent.config = None
        self.mock_agent.templates.filter.return_value.values.return_value = []
        self.mock_agent.ignore_templates = False

        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "abandoned_cart",
            "contact_urn": "whatsapp:5511",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}

    def test_execute_propagates_context_for_cart_abandonment(self):
        request_data = RequestData(
            params={},
            payload={"order_form_id": "of-cart-1", "phone_number": "5511"},
        )

        self.usecase.execute(self.mock_agent, request_data)

        _, call_kwargs = self.mock_broadcast_handler.send_message.call_args
        self.assertEqual(
            call_kwargs["dispatch_context"],
            BroadcastDispatchContext(order_form_id="of-cart-1"),
        )

    def test_execute_propagates_context_for_order_status(self):
        request_data = RequestData(
            params={},
            payload={"OrderId": "order-99", "Domain": "Marketplace"},
        )

        self.usecase.execute(self.mock_agent, request_data)

        _, call_kwargs = self.mock_broadcast_handler.send_message.call_args
        self.assertEqual(
            call_kwargs["dispatch_context"],
            BroadcastDispatchContext(order_id="order-99"),
        )

    def test_execute_propagates_none_when_payload_has_no_commercial_keys(self):
        request_data = RequestData(params={}, payload={"phone_number": "5511"})

        self.usecase.execute(self.mock_agent, request_data)

        _, call_kwargs = self.mock_broadcast_handler.send_message.call_args
        self.assertIsNone(call_kwargs["dispatch_context"])
