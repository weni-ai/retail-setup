from django.test import TestCase
from unittest.mock import MagicMock, patch
from uuid import uuid4

from retail.agents.models import IntegratedAgent
from retail.agents.usecases.agent_webhook import (
    AgentWebhookUseCase,
    LambdaHandler,
    BroadcastHandler,
    LambdaResponseStatus,
)
from retail.templates.models import Template
from retail.agents.tests.mocks.cache.integrated_agent_webhook import (
    IntegratedAgentCacheHandlerMock,
)


class AgentWebhookUseCaseTest(TestCase):
    def setUp(self):
        # Mock the datalake audit function
        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_handler = MagicMock()
        self.mock_broadcast_handler = MagicMock()
        self.mock_cache_handler = IntegratedAgentCacheHandlerMock()

        self.usecase = AgentWebhookUseCase(
            lambda_handler=self.mock_lambda_handler,
            broadcast_handler=self.mock_broadcast_handler,
            cache_handler=self.mock_cache_handler,
        )
        self.mock_agent = MagicMock()
        self.mock_agent.uuid = uuid4()
        self.mock_agent.ignore_templates = False
        self.mock_agent.project.uuid = uuid4()
        self.mock_agent.project.vtex_account = "test_account"
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

    @patch("retail.agents.usecases.agent_webhook.IntegratedAgent.objects.get")
    def test_get_integrated_agent_found(self, mock_get):
        mock_agent = MagicMock()
        mock_get.return_value = mock_agent
        test_uuid = uuid4()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)

    @patch("retail.agents.usecases.agent_webhook.IntegratedAgent.objects.get")
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

        self.assertIsNone(result)
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

    @patch("retail.agents.usecases.agent_webhook.IntegratedAgent.objects.get")
    def test_get_integrated_agent_from_cache(self, mock_get):
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid

        self.mock_cache_handler.set_cached_agent(mock_agent)

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_not_called()

    @patch("retail.agents.usecases.agent_webhook.IntegratedAgent.objects.get")
    def test_get_integrated_agent_cache_miss_then_set(self, mock_get):
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid
        mock_get.return_value = mock_agent

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertEqual(cached_agent, mock_agent)

    @patch("retail.agents.usecases.agent_webhook.IntegratedAgent.objects.get")
    def test_get_integrated_agent_cache_miss_not_found(self, mock_get):
        mock_get.side_effect = IntegratedAgent.DoesNotExist()
        test_uuid = uuid4()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertIsNone(result)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)
        cached_agent = self.mock_cache_handler.get_cached_agent(test_uuid)
        self.assertIsNone(cached_agent)

    @patch("retail.agents.usecases.agent_webhook.IntegratedAgent.objects.get")
    def test_get_integrated_agent_cache_with_none_value(self, mock_get):
        mock_agent = MagicMock()
        test_uuid = uuid4()
        mock_agent.uuid = test_uuid
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


class LambdaHandlerTest(TestCase):
    def setUp(self):
        # Mock the datalake audit function
        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_service = MagicMock()
        self.handler = LambdaHandler(lambda_service=self.mock_lambda_service)
        self.mock_agent = MagicMock()
        self.mock_agent.agent.lambda_arn = (
            "arn:aws:lambda:region:account-id:function:function-name"
        )
        self.mock_agent.project.uuid = uuid4()
        self.mock_agent.project.vtex_account = "test_account"
        self.mock_agent.ignore_templates = False
        self.mock_agent.global_rule_code = ""

    def test_invoke_lambda(self):
        mock_data = MagicMock()
        mock_data.configure_mock(
            params={"param1": "value1"},
            payload={"payload_key": "payload_value"},
            credentials={"cred_key": "cred_value"},
            project_rules=[],
        )

        expected_payload = {
            "params": mock_data.params,
            "payload": mock_data.payload,
            "credentials": mock_data.credentials,
            "ignore_official_rules": self.mock_agent.ignore_templates,
            "global_rule": self.mock_agent.global_rule_code,
            "project_rules": [],
            "project": {
                "uuid": str(self.mock_agent.project.uuid),
                "vtex_account": self.mock_agent.project.vtex_account,
            },
        }

        self.handler.invoke(self.mock_agent, mock_data)

        self.mock_lambda_service.invoke.assert_called_once_with(
            self.mock_agent.agent.lambda_arn, expected_payload
        )

    def test_parse_response_success(self):
        payload_json = MagicMock()
        payload_json.read.return_value = b'{"template": "order_update"}'
        response = {"Payload": payload_json}

        result = self.handler.parse_response(response)

        self.assertEqual(result, {"template": "order_update"})

    def test_parse_response_json_decode_error(self):
        payload_json = MagicMock()
        payload_json.read.return_value = b"invalid json"
        response = {"Payload": payload_json}

        result = self.handler.parse_response(response)

        self.assertIsNone(result)

    def test_validate_response_rule_matched(self):
        data = {"status": LambdaResponseStatus.RULE_MATCHED}

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertTrue(result)

    def test_validate_response_rule_not_matched(self):
        data = {
            "status": LambdaResponseStatus.RULE_NOT_MATCHED,
            "error": "No rule matched",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_pre_processing_failed(self):
        data = {
            "status": LambdaResponseStatus.PRE_PROCESSING_FAILED,
            "error": "Pre-processing error",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_custom_rule_failed(self):
        data = {
            "status": LambdaResponseStatus.CUSTOM_RULE_FAILED,
            "error": "Custom rule error",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_official_rule_failed(self):
        data = {
            "status": LambdaResponseStatus.OFFICIAL_RULE_FAILED,
            "error": "Official rule error",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_unknown_status_code(self):
        data = {"status": 999, "error": "Unknown error"}

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_error_message(self):
        data = {"errorMessage": "Some error"}

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_no_status_no_error_message(self):
        data = {"template": "order_update", "contact_urn": "whatsapp:123"}

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)


class BroadcastHandlerTest(TestCase):
    def setUp(self):
        self.mock_flows_service = MagicMock()
        self.mock_audit = MagicMock()
        self.handler = BroadcastHandler(
            flows_service=self.mock_flows_service, audit_func=self.mock_audit
        )
        self.mock_agent = MagicMock()
        self.mock_agent.uuid = uuid4()
        self.mock_agent.channel_uuid = uuid4()
        self.mock_agent.project.uuid = uuid4()
        self.mock_agent.config = None

    def test_can_send_to_contact_no_config(self):
        self.mock_agent.config = None
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_empty_config(self):
        self.mock_agent.config = {}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_contact_urn(self):
        data = {}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_integration_settings(self):
        self.mock_agent.config = {"other_settings": {}}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_order_status_restriction(self):
        self.mock_agent.config = {"integration_settings": {"other_restriction": {}}}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_inactive(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": False,
                    "allowed_phone_numbers": ["whatsapp:123"],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_allowed(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                    "allowed_phone_numbers": ["whatsapp:123"],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_blocked(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                    "allowed_phone_numbers": ["whatsapp:999"],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_no_allowed_numbers(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                    "allowed_phone_numbers": [],
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_missing_allowed_numbers(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertFalse(self.handler.can_send_to_contact(self.mock_agent, data))

    def test_get_current_template_name_success(self):
        data = {"template": "order_update"}
        mock_template = MagicMock()
        mock_template.current_version.template_name = "order_update_v2"
        self.mock_agent.templates.get.return_value = mock_template

        result = self.handler.get_current_template_name(self.mock_agent, data)

        self.assertEqual(result, "order_update_v2")
        self.mock_agent.templates.get.assert_called_once_with(name="order_update")

    def test_get_current_template_name_not_found(self):
        data = {"template": "non_existent_template"}
        self.mock_agent.templates.get.side_effect = Template.DoesNotExist()

        result = self.handler.get_current_template_name(self.mock_agent, data)

        self.assertIsNone(result)

    def test_get_current_template_name_no_current_version(self):
        data = {"template": "order_update"}
        mock_template = MagicMock()
        mock_template.current_version = None
        self.mock_agent.templates.get.return_value = mock_template

        result = self.handler.get_current_template_name(self.mock_agent, data)

        self.assertFalse(result)
        self.mock_agent.templates.get.assert_called_once_with(name="order_update")

    def test_send_message(self):
        message = {"template": "test", "contact": "whatsapp:123"}
        mock_agent = MagicMock()
        lambda_data = {
            "status": 0,  # RULE_MATCHED
            "template": "test",
            "contact_urn": "whatsapp:123",
            "template_variables": ["var1", "value1"],
        }

        self.handler.send_message(message, mock_agent, lambda_data)

        self.mock_flows_service.send_whatsapp_broadcast.assert_called_once_with(message)

    def test_build_message_success(self):
        data = {"template": "order_update", "contact_urn": "whatsapp:123"}
        mock_template = MagicMock()
        mock_template.current_version.template_name = "order_update_v2"
        self.mock_agent.templates.get.return_value = mock_template

        with patch(
            "retail.agents.usecases.agent_webhook.build_broadcast_template_message",
            return_value={"msg": "ok"},
        ) as mock_build:
            result = self.handler.build_message(self.mock_agent, data)

            self.assertEqual(result, {"msg": "ok"})
            mock_build.assert_called_once_with(
                data=data,
                channel_uuid=str(self.mock_agent.channel_uuid),
                project_uuid=str(self.mock_agent.project.uuid),
                template_name="order_update_v2",
            )

    def test_build_message_template_not_found(self):
        data = {"template": "non_existent_template"}
        self.mock_agent.templates.get.side_effect = Template.DoesNotExist()

        result = self.handler.build_message(self.mock_agent, data)

        self.assertIsNone(result)

    def test_register_broadcast_event_with_lambda_data(self):
        """Test that _register_broadcast_event correctly extracts data from lambda_data."""
        message = {
            "msg": {
                "template": {"name": "message_template", "variables": ["var1", "var2"]}
            },
            "urns": ["whatsapp:123456789"],
        }
        response = {"status": "success"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        lambda_data = {
            "status": 0,  # RULE_MATCHED
            "template": "lambda_template",
            "template_variables": ["var1", "value1", "var2", "value2"],
            "contact_urn": "whatsapp:987654321",
        }

        # Capture the data passed to audit_func
        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(
            message, response, mock_agent, lambda_data
        )

        # Verify that lambda_data was used for status, template, contact_urn, but template_variables come from message
        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertEqual(event_data["status"], 0)  # From lambda_data
        self.assertEqual(event_data["template"], "lambda_template")  # From lambda_data
        self.assertEqual(
            event_data["contact_urn"], "whatsapp:987654321"
        )  # From lambda_data
        self.assertEqual(
            event_data["template_variables"], ["var1", "var2"]
        )  # From message
        self.assertEqual(event_data["project"], "project-uuid")
        self.assertEqual(event_data["agent"], "agent-uuid")
        self.assertEqual(event_data["request"], message)
        self.assertEqual(event_data["response"], response)
        self.assertEqual(event_data["data"], {"event_type": "template_broadcast_sent"})

    def test_register_broadcast_event_without_lambda_data(self):
        """Test that _register_broadcast_event falls back to message data when lambda_data is None."""
        message = {
            "msg": {
                "template": {"name": "message_template", "variables": ["var1", "var2"]}
            },
            "urns": ["whatsapp:123456789"],
        }
        response = {"status": "success"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        # Capture the data passed to audit_func
        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(message, response, mock_agent, None)

        # Verify that message data was used as fallback
        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertNotIn("status", event_data)  # No status when no lambda_data
        self.assertEqual(event_data["template"], "message_template")  # From message
        self.assertEqual(
            event_data["contact_urn"], "whatsapp:123456789"
        )  # From message
        self.assertEqual(
            event_data["template_variables"], ["var1", "var2"]
        )  # From message
        self.assertEqual(event_data["project"], "project-uuid")
        self.assertEqual(event_data["agent"], "agent-uuid")
        self.assertEqual(event_data["data"], {"event_type": "template_broadcast_sent"})

    def test_register_broadcast_event_with_error(self):
        """Test that _register_broadcast_event correctly handles error data."""
        message = {
            "msg": {
                "template": {"name": "message_template", "variables": ["var1", "var2"]}
            },
            "urns": ["whatsapp:123456789"],
        }
        response = {"error": "Some error occurred"}
        mock_agent = MagicMock()
        mock_agent.project.uuid = "project-uuid"
        mock_agent.agent.uuid = "agent-uuid"

        lambda_data = {
            "status": 2,  # PREPROCESSING_FAILED
            "template": "lambda_template",
            "template_variables": ["var1", "value1"],
            "contact_urn": "whatsapp:987654321",
        }

        # Capture the data passed to audit_func
        audit_calls = []

        def mock_audit_func(path, data):
            audit_calls.append(data)

        self.mock_audit.side_effect = mock_audit_func

        self.handler._register_broadcast_event(
            message, response, mock_agent, lambda_data
        )

        # Verify that error data was captured correctly
        self.assertEqual(len(audit_calls), 1)
        event_data = audit_calls[0]

        self.assertEqual(event_data["status"], 2)  # PREPROCESSING_FAILED
        self.assertEqual(event_data["error"], ["Some error occurred"])  # Error as list
        self.assertEqual(event_data["data"], {"event_type": "template_broadcast_sent"})
