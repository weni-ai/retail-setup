from django.test import TestCase

from unittest.mock import MagicMock, patch

from uuid import uuid4

from retail.agents.assign.models import IntegratedAgent
from retail.agents.webhooks.usecases.agent_webhook import AgentWebhookUseCase
from retail.templates.models import Template


class AgentWebhookUseCaseTest(TestCase):
    def setUp(self):
        # Mock services
        self.mock_lambda_service = MagicMock()
        self.mock_flows_service = MagicMock()
        self.usecase = AgentWebhookUseCase(
            lambda_service=self.mock_lambda_service,
            flows_service=self.mock_flows_service,
        )
        # Mock agent
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

    def test_can_send_to_contact_no_config(self):
        self.mock_agent.config = None
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.usecase._can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_empty_config(self):
        self.mock_agent.config = {}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.usecase._can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_contact_urn(self):
        data = {}
        self.assertFalse(self.usecase._can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_integration_settings(self):
        self.mock_agent.config = {"other_settings": {}}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.usecase._can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_no_order_status_restriction(self):
        self.mock_agent.config = {"integration_settings": {"other_restriction": {}}}
        data = {"contact_urn": "whatsapp:123"}
        self.assertTrue(self.usecase._can_send_to_contact(self.mock_agent, data))

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
        self.assertTrue(self.usecase._can_send_to_contact(self.mock_agent, data))

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
        self.assertTrue(self.usecase._can_send_to_contact(self.mock_agent, data))

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
        self.assertFalse(self.usecase._can_send_to_contact(self.mock_agent, data))

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
        self.assertFalse(self.usecase._can_send_to_contact(self.mock_agent, data))

    def test_can_send_to_contact_restriction_active_missing_allowed_numbers(self):
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                }
            }
        }
        data = {"contact_urn": "whatsapp:123"}
        self.assertFalse(self.usecase._can_send_to_contact(self.mock_agent, data))

    def test_get_integrated_agent_blocked_uuid(self):
        blocked_uuid = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"
        result = self.usecase._get_integrated_agent(blocked_uuid)
        self.assertIsNone(result)

    @patch("retail.agents.webhooks.usecases.agent_webhook.IntegratedAgent.objects.get")
    def test_get_integrated_agent_found(self, mock_get):
        mock_agent = MagicMock()
        mock_get.return_value = mock_agent
        test_uuid = uuid4()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertEqual(result, mock_agent)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)

    @patch("retail.agents.webhooks.usecases.agent_webhook.IntegratedAgent.objects.get")
    def test_get_integrated_agent_not_found(self, mock_get):
        mock_get.side_effect = IntegratedAgent.DoesNotExist()
        test_uuid = uuid4()

        result = self.usecase._get_integrated_agent(test_uuid)

        self.assertIsNone(result)
        mock_get.assert_called_once_with(uuid=test_uuid, is_active=True)

    def test_invoke_lambda(self):
        mock_data = MagicMock()
        mock_data.params = {"param1": "value1"}
        mock_data.payload = {"payload_key": "payload_value"}
        mock_data.credentials = {"cred_key": "cred_value"}

        expected_payload = {
            "params": mock_data.params,
            "payload": mock_data.payload,
            "credentials": mock_data.credentials,
            "ignore_official_rules": self.mock_agent.ignore_templates,
            "project": {
                "uuid": str(self.mock_agent.project.uuid),
                "vtex_account": self.mock_agent.project.vtex_account,
            },
        }

        self.usecase._invoke_lambda(self.mock_agent, mock_data)

        self.mock_lambda_service.invoke.assert_called_once_with(
            self.mock_agent.agent.lambda_arn, expected_payload
        )

    def test_get_current_template_name_success(self):
        data = {"template": "order_update"}
        mock_template = MagicMock()
        mock_template.current_version.template_name = "order_update_v2"
        self.mock_agent.templates.get.return_value = mock_template

        result = self.usecase._get_current_template_name(self.mock_agent, data)

        self.assertEqual(result, "order_update_v2")
        self.mock_agent.templates.get.assert_called_once_with(name="order_update")

    def test_get_current_template_name_not_found(self):
        data = {"template": "non_existent_template"}
        self.mock_agent.templates.get.side_effect = Template.DoesNotExist()

        result = self.usecase._get_current_template_name(self.mock_agent, data)

        self.assertIsNone(result)

    def test_get_current_template_name_no_template_in_data(self):
        data = {}

        result = self.usecase._get_current_template_name(self.mock_agent, data)

        # When template is None, the method will try to get a template with name=None
        # and since we have a mock that returns template_v1, we need to adjust the test
        self.mock_agent.templates.get.assert_called_once_with(name=None)
        self.assertEqual(result, "template_v1")

    def test_send_broadcast_message(self):
        message = {"template": "test", "contact": "whatsapp:123"}

        self.usecase._send_broadcast_message(message)

        self.mock_flows_service.send_whatsapp_broadcast.assert_called_once_with(message)

    def test_execute_successful(self):
        payload_json = MagicMock()
        payload_json.read.return_value = (
            b'{"template": "order_update", "contact_urn": "whatsapp:123"}'
        )
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = None
        self.mock_flows_service.send_whatsapp_broadcast.return_value = {"status": "ok"}

        with patch(
            "retail.agents.webhooks.usecases.agent_webhook.build_broadcast_template_message",
            return_value={"msg": "ok"},
        ):
            result = self.usecase.execute(self.mock_agent, MagicMock())
            self.assertIsInstance(result, dict)
            self.mock_flows_service.send_whatsapp_broadcast.assert_called_once()

    def test_execute_should_not_send_broadcast(self):
        self.mock_agent.contact_percentage = 0
        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_missing_template_error(self):
        payload_json = MagicMock()
        payload_json.read.return_value = b'{"error": "Missing template"}'
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = None
        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_contact_not_allowed(self):
        payload_json = MagicMock()
        payload_json.read.return_value = (
            b'{"template": "order_update", "contact_urn": "whatsapp:123"}'
        )
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = {
            "integration_settings": {
                "order_status_restriction": {
                    "is_active": True,
                    "allowed_phone_numbers": ["whatsapp:999"],
                }
            }
        }
        result = self.usecase.execute(self.mock_agent, MagicMock())
        self.assertIsNone(result)

    def test_execute_lambda_error_message(self):
        payload_json = MagicMock()
        payload_json.read.return_value = b'{"errorMessage": "Some error"}'
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = None
        with patch(
            "retail.agents.webhooks.usecases.agent_webhook.build_broadcast_template_message"
        ):
            result = self.usecase.execute(self.mock_agent, MagicMock())
            self.assertIsNone(result)

    def test_execute_template_not_found(self):
        payload_json = MagicMock()
        payload_json.read.return_value = (
            b'{"template": "not_found", "contact_urn": "whatsapp:123"}'
        )
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = None
        self.mock_agent.templates.get.side_effect = Template.DoesNotExist()
        with patch(
            "retail.agents.webhooks.usecases.agent_webhook.build_broadcast_template_message"
        ):
            result = self.usecase.execute(self.mock_agent, MagicMock())
            self.assertIsInstance(result, dict)

    def test_execute_build_message_exception(self):
        payload_json = MagicMock()
        payload_json.read.return_value = (
            b'{"template": "order_update", "contact_urn": "whatsapp:123"}'
        )
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = None

        with patch(
            "retail.agents.webhooks.usecases.agent_webhook.build_broadcast_template_message",
            side_effect=Exception("Build message error"),
        ):
            result = self.usecase.execute(self.mock_agent, MagicMock())
            self.assertIsInstance(result, dict)

    def test_execute_build_message_returns_none(self):
        payload_json = MagicMock()
        payload_json.read.return_value = (
            b'{"template": "order_update", "contact_urn": "whatsapp:123"}'
        )
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = None

        with patch(
            "retail.agents.webhooks.usecases.agent_webhook.build_broadcast_template_message",
            return_value=None,
        ):
            result = self.usecase.execute(self.mock_agent, MagicMock())
            self.assertIsInstance(result, dict)
            self.mock_flows_service.send_whatsapp_broadcast.assert_not_called()

    def test_execute_build_message_returns_empty_dict(self):
        payload_json = MagicMock()
        payload_json.read.return_value = (
            b'{"template": "order_update", "contact_urn": "whatsapp:123"}'
        )
        self.mock_lambda_service.invoke.return_value = {"Payload": payload_json}
        self.mock_agent.config = None

        with patch(
            "retail.agents.webhooks.usecases.agent_webhook.build_broadcast_template_message",
            return_value={},
        ):
            result = self.usecase.execute(self.mock_agent, MagicMock())
            self.assertIsInstance(result, dict)
            self.mock_flows_service.send_whatsapp_broadcast.assert_not_called()
