from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.services.broadcast import (
    BroadcastDispatchResult,
)
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


def _dispatch_result(response=None, broadcast_message_uuid=None):
    """Build a ``BroadcastDispatchResult`` with sensible defaults.

    Centralised here so the matrix of webhook-usecase tests doesn't
    repeat the dataclass construction noise. Defaults keep the tests
    that don't care about the persisted ``BroadcastMessage`` UUID
    short.
    """
    return BroadcastDispatchResult(
        response=response if response is not None else {},
        broadcast_message_uuid=broadcast_message_uuid,
    )


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
        parsed_payload = {
            "template": "order_update",
            "contact_urn": "whatsapp:123",
        }
        self.mock_lambda_handler.invoke.return_value = mock_response
        self.mock_lambda_handler.parse_response.return_value = parsed_payload
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}

        result = self.usecase.execute(self.mock_agent, MagicMock())

        # On success, execute returns the parsed Lambda payload so callers
        # (e.g. the cart abandonment service) can tell that the broadcast was
        # dispatched and read the template/contact_urn directly.
        self.assertEqual(result, parsed_payload)
        self.mock_broadcast_handler.send_message.assert_called_once()

    def test_execute_should_not_send_broadcast(self):
        self.mock_agent.contact_percentage = 0
        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

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


class AgentWebhookUseCaseLoggingTest(TestCase):
    """Pin the exec_logger.* contract added in feat/add-logging-config.

    The mock logger is injected into ``AgentWebhookUseCase`` via its
    constructor so we can assert which logging method fires for every
    branch of ``execute`` / ``_process_lambda_response``.
    """

    def setUp(self):
        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_handler = MagicMock()
        self.mock_broadcast_handler = MagicMock()
        self.mock_cache_handler = IntegratedAgentCacheHandlerMock()

        self.exec_logger = MagicMock()
        self.usecase = AgentWebhookUseCase(
            active_agent=self.mock_lambda_handler,
            broadcast=self.mock_broadcast_handler,
            cache=self.mock_cache_handler,
            exec_logger=self.exec_logger,
        )

        # Tests below assert the exact kwargs passed to log_lambda_response;
        # default the new log_tail input to None so individual tests only
        # opt into it when they explicitly exercise the LogResult path.
        self.mock_lambda_handler.parse_log_tail.return_value = None

        self.mock_agent = MagicMock()
        self.mock_agent.uuid = uuid4()
        self.mock_agent.contact_percentage = 100
        self.mock_agent.config = None
        self.mock_agent.templates.filter.return_value.values.return_value = []
        self.mock_agent.credentials.all.return_value = []

    def _build_request_data(self, params=None, payload=None):
        data = MagicMock()
        data.params = params if params is not None else {"k": "v"}
        data.payload = payload if payload is not None else {"event": "order"}
        data.project_rules = None

        def _set_project_rules(rules):
            data.project_rules = rules

        data.set_project_rules.side_effect = _set_project_rules
        return data

    def test_execute_logs_skip_when_contact_percentage_blocks(self):
        self.mock_agent.contact_percentage = 0

        result = self.usecase.execute(self.mock_agent, self._build_request_data())

        self.assertIsNone(result)
        self.exec_logger.log_execution_skip.assert_called_once_with(
            reason="Broadcast not allowed (contact percentage check)",
            skip_data={"contact_percentage": 0},
        )
        self.exec_logger.log_lambda_request.assert_not_called()
        self.exec_logger.log_lambda_response.assert_not_called()

    def test_execute_logs_lambda_request_with_params_payload_and_project_rules(self):
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={"id": 7}
        )
        template = MagicMock()
        template.uuid = uuid4()
        self.mock_broadcast_handler.get_current_template.return_value = template

        params = {"foo": "bar"}
        payload = {"order": "123"}
        data = self._build_request_data(params=params, payload=payload)

        self.usecase.execute(self.mock_agent, data)

        self.exec_logger.log_lambda_request.assert_called_once_with(
            request_data={
                "params": params,
                "payload": payload,
                "project_rules": [],
            },
        )

    def test_execute_logs_lambda_response_with_parsed_payload(self):
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={"id": 1}
        )
        self.mock_broadcast_handler.get_current_template.return_value = MagicMock(
            uuid=uuid4()
        )

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_lambda_response.assert_called_once_with(
            response_data=parsed,
            log_tail=None,
        )

    def test_execute_forwards_lambda_log_tail_to_log_lambda_response(self):
        # parse_log_tail decodes the LogResult tail returned by AWS when
        # the invoke uses LogType="Tail"; the use case must hand it to
        # the exec_logger so the LAMBDA_RESPONSE trace records the
        # function's prints alongside the parsed payload.
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        invoke_response = {"Payload": MagicMock(), "LogResult": "encoded-bytes"}
        self.mock_lambda_handler.invoke.return_value = invoke_response
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.parse_log_tail.return_value = (
            "START RequestId: abc\nhello from print\nEND RequestId: abc\n"
        )
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={"id": 1}
        )
        self.mock_broadcast_handler.get_current_template.return_value = MagicMock(
            uuid=uuid4()
        )

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.mock_lambda_handler.parse_log_tail.assert_called_once_with(
            invoke_response
        )
        self.exec_logger.log_lambda_response.assert_called_once_with(
            response_data=parsed,
            log_tail="START RequestId: abc\nhello from print\nEND RequestId: abc\n",
        )

    def test_execute_logs_update_contact_urn_when_payload_has_it(self):
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
            "contact_urn": "whatsapp:5511999999999",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={"id": 1}
        )
        self.mock_broadcast_handler.get_current_template.return_value = MagicMock(
            uuid=uuid4()
        )

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.update_contact_urn.assert_called_once_with(
            contact_urn="whatsapp:5511999999999",
        )

    def test_execute_does_not_log_update_contact_urn_when_payload_missing_it(self):
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = {
            "template": "order_update",
        }
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={"id": 1}
        )
        self.mock_broadcast_handler.get_current_template.return_value = MagicMock(
            uuid=uuid4()
        )

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.update_contact_urn.assert_not_called()

    def test_execute_logs_lambda_response_with_error_fallback_when_parse_returns_none(
        self,
    ):
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = None

        result = self.usecase.execute(self.mock_agent, self._build_request_data())

        self.assertIsNone(result)
        self.exec_logger.log_lambda_response.assert_called_once_with(
            response_data={"error": "Failed to parse response"},
            log_tail=None,
        )
        self.exec_logger.log_execution_error.assert_called_once_with(
            error_message="Error parsing lambda response",
        )
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_logs_skip_when_validation_fails(self):
        parsed = {"status": "ERROR", "error": "boom"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = False

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_execution_skip.assert_called_once_with(
            reason="Lambda response validation failed",
            skip_data={"status": "ERROR", "error": "boom"},
        )
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_logs_skip_when_contact_not_allowed(self):
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = False

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_execution_skip.assert_called_once_with(
            reason="Contact not allowed to receive broadcast",
            skip_data={"contact_urn": "whatsapp:123"},
        )
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_logs_error_when_build_message_returns_none(self):
        parsed = {"template": "missing_one", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = None

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_execution_error.assert_called_once_with(
            error_message="Failed to build broadcast message",
            error_data={"payload_data": {"template": "missing_one", "contact_urn": "whatsapp:123"}},
        )
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_logs_error_when_build_message_returns_empty_dict(self):
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {}

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_execution_error.assert_called_once_with(
            error_message="Failed to build broadcast message",
            error_data={"payload_data": {"template": "order_update", "contact_urn": "whatsapp:123"}},
        )
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_logs_broadcast_sent_with_id_and_template_uuid(self):
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}

        broadcast_response = {"id": 42, "status": "queued"}
        broadcast_message_uuid = uuid4()
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response=broadcast_response,
            broadcast_message_uuid=broadcast_message_uuid,
        )
        template = MagicMock()
        template_uuid = uuid4()
        template.uuid = template_uuid
        self.mock_broadcast_handler.get_current_template.return_value = template

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_broadcast_sent.assert_called_once_with(
            broadcast_response=broadcast_response,
            template_uuid=template_uuid,
            broadcast_id=42,
            broadcast_message_uuid=broadcast_message_uuid,
        )
        self.exec_logger.log_execution_error.assert_not_called()

    def test_execute_logs_broadcast_sent_when_dispatch_persistence_failed(self):
        # ``Broadcast.send_message`` is defensive on the BroadcastMessage
        # persistence path: when ``RecordBroadcastSentUseCase`` fails the
        # dispatch result still carries the Flows response but the UUID
        # is ``None``. The execution log records success but the FK
        # stays unlinked.
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={}, broadcast_message_uuid=None
        )
        self.mock_broadcast_handler.get_current_template.return_value = None

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_broadcast_sent.assert_called_once_with(
            broadcast_response={},
            template_uuid=None,
            broadcast_id=None,
            broadcast_message_uuid=None,
        )
        self.exec_logger.log_execution_error.assert_not_called()

    def test_execute_logs_broadcast_sent_with_none_template_uuid_when_template_is_false(
        self,
    ):
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        broadcast_message_uuid = uuid4()
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={"id": 9},
            broadcast_message_uuid=broadcast_message_uuid,
        )
        self.mock_broadcast_handler.get_current_template.return_value = False

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_broadcast_sent.assert_called_once_with(
            broadcast_response={"id": 9},
            template_uuid=None,
            broadcast_id=9,
            broadcast_message_uuid=broadcast_message_uuid,
        )

    def test_execute_logs_error_when_build_message_raises(self):
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.side_effect = RuntimeError("kaboom")

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_execution_error.assert_called_once_with(
            error_message="Error building/sending broadcast: kaboom",
        )
        self.exec_logger.log_broadcast_sent.assert_not_called()
        self.mock_broadcast_handler.send_message.assert_not_called()

    def test_execute_logs_error_when_send_message_raises(self):
        parsed = {"template": "order_update", "contact_urn": "whatsapp:123"}
        self.mock_lambda_handler.invoke.return_value = {"Payload": MagicMock()}
        self.mock_lambda_handler.parse_response.return_value = parsed
        self.mock_lambda_handler.validate_response.return_value = True
        self.mock_broadcast_handler.can_send_to_contact.return_value = True
        self.mock_broadcast_handler.build_message.return_value = {"msg": "ok"}
        self.mock_broadcast_handler.send_message.side_effect = RuntimeError(
            "flows down"
        )

        self.usecase.execute(self.mock_agent, self._build_request_data())

        self.exec_logger.log_execution_error.assert_called_once_with(
            error_message="Error building/sending broadcast: flows down",
        )
        self.exec_logger.log_broadcast_sent.assert_not_called()

    def test_execute_logs_unhandled_exception_and_reraises(self):
        """An exception that doesn't have its own try/except (e.g. raised from
        ``_set_project_rules``) must still produce an error trace
        before propagating, so the row never lingers at ``processing``.
        """
        # Force ``_set_project_rules`` to blow up by making the templates
        # filter raise — that sits between the contact-percentage check
        # and the lambda-request log, so neither a skip nor a normal
        # error trace would otherwise fire.
        self.mock_agent.templates.filter.side_effect = RuntimeError(
            "templates lookup boom"
        )

        with self.assertRaises(RuntimeError) as ctx:
            self.usecase.execute(self.mock_agent, self._build_request_data())

        self.assertEqual(str(ctx.exception), "templates lookup boom")
        self.exec_logger.log_execution_error.assert_called_once_with(
            error_message="templates lookup boom",
            error_data={"phase": "agent_webhook_execute"},
        )
        # We bailed before any of the inner branches got a chance to fire.
        self.exec_logger.log_lambda_request.assert_not_called()
        self.exec_logger.log_lambda_response.assert_not_called()
        self.exec_logger.log_broadcast_sent.assert_not_called()
        self.exec_logger.log_execution_skip.assert_not_called()


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

        self.exec_logger = MagicMock()
        self.usecase = AgentWebhookUseCase(
            active_agent=self.mock_lambda_handler,
            broadcast=self.mock_broadcast_handler,
            cache=self.mock_cache_handler,
            exec_logger=self.exec_logger,
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
        self.mock_broadcast_handler.send_message.return_value = _dispatch_result(
            response={"id": 1}
        )
        self.mock_broadcast_handler.get_current_template.return_value = MagicMock(
            uuid=uuid4()
        )

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


class AgentWebhookUseCaseExecuteFromTaskTests(TestCase):
    """Orchestration tests for ``execute_from_task``.

    The method centralises the resolve-agent / forward-UUID /
    dispatch flow that used to live in ``task_agent_webhook``: the
    contextvar wiring, the "open new row vs reuse forwarded UUID"
    branch, and the credential assembly all live here.
    """

    def setUp(self):
        super().setUp()
        from retail.agents.domains.agent_execution.context import (
            clear_execution_context,
        )

        clear_execution_context()
        self.addCleanup(clear_execution_context)

        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_handler = MagicMock()
        self.mock_broadcast_handler = MagicMock()
        self.mock_cache_handler = IntegratedAgentCacheHandlerMock()
        self.mock_exec_logger = MagicMock()

        self.usecase = AgentWebhookUseCase(
            active_agent=self.mock_lambda_handler,
            broadcast=self.mock_broadcast_handler,
            cache=self.mock_cache_handler,
            exec_logger=self.mock_exec_logger,
        )

    def _patch_agent_lookup(self, agent_or_none):
        return patch.object(
            self.usecase, "_get_integrated_agent", return_value=agent_or_none
        )

    def test_missing_agent_without_forwarded_uuid_does_not_open_row(self):
        with self._patch_agent_lookup(None):
            result = self.usecase.execute_from_task(
                integrated_agent_uuid=str(uuid4()),
                payload={"a": 1},
                params={},
            )

        self.assertIsNone(result)
        self.mock_exec_logger.log_webhook_received.assert_not_called()
        self.mock_exec_logger.log_execution_skip.assert_not_called()

    def test_missing_agent_with_forwarded_uuid_logs_skip_on_forwarded_row(self):
        forwarded_uuid = uuid4()
        agent_uuid_str = str(uuid4())

        with self._patch_agent_lookup(None):
            self.usecase.execute_from_task(
                integrated_agent_uuid=agent_uuid_str,
                payload={"a": 1},
                params={},
                forwarded_execution_uuid=str(forwarded_uuid),
            )

        self.mock_exec_logger.log_webhook_received.assert_not_called()
        self.mock_exec_logger.log_execution_skip.assert_called_once_with(
            execution_uuid=forwarded_uuid,
            reason="integrated_agent_missing_or_blocked",
            skip_data={"integrated_agent_uuid": agent_uuid_str},
        )

    def _build_agent(self):
        agent = MagicMock(uuid=uuid4(), ignore_templates=[])
        # ``execute()`` reads ``contact_percentage`` against ``<= 0`` so
        # MagicMock's default is a comparison error; pin it to 0 so the
        # call returns early without exercising the full flow.
        agent.contact_percentage = 0
        agent.credentials.all.return_value = []
        return agent

    def test_no_forwarded_uuid_opens_a_new_execution_row(self):
        agent = self._build_agent()

        with self._patch_agent_lookup(agent):
            self.usecase.execute_from_task(
                integrated_agent_uuid=str(agent.uuid),
                payload={"a": 1},
                params={},
            )

        self.mock_exec_logger.log_webhook_received.assert_called_once()
        call_kwargs = self.mock_exec_logger.log_webhook_received.call_args.kwargs
        self.assertIs(call_kwargs["integrated_agent"], agent)
        self.assertEqual(call_kwargs["payload"], {"a": 1})

    def test_forwarded_uuid_skips_log_webhook_received(self):
        from retail.agents.domains.agent_execution.context import (
            get_current_execution_uuid,
        )

        agent = self._build_agent()
        forwarded_uuid = uuid4()

        with self._patch_agent_lookup(agent):
            self.usecase.execute_from_task(
                integrated_agent_uuid=str(agent.uuid),
                payload={"a": 1},
                params={},
                forwarded_execution_uuid=str(forwarded_uuid),
            )

        self.mock_exec_logger.log_webhook_received.assert_not_called()
        # The forwarded UUID must land in the contextvar so downstream
        # logging picks it up automatically.
        self.assertEqual(get_current_execution_uuid(), forwarded_uuid)

    def test_string_forwarded_uuid_is_parsed_into_uuid_instance(self):
        from retail.agents.domains.agent_execution.context import (
            get_current_execution_uuid,
        )

        agent = self._build_agent()
        forwarded_uuid = uuid4()

        with self._patch_agent_lookup(agent):
            self.usecase.execute_from_task(
                integrated_agent_uuid=str(agent.uuid),
                payload={"a": 1},
                params={},
                forwarded_execution_uuid=str(forwarded_uuid),
            )

        ctx = get_current_execution_uuid()
        from uuid import UUID as _UUID

        self.assertIsInstance(ctx, _UUID)
        self.assertEqual(ctx, forwarded_uuid)
