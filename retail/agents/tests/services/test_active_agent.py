from django.test import TestCase

from unittest.mock import MagicMock, patch

from uuid import uuid4

from retail.agents.domains.agent_webhook.services.active_agent import (
    ActiveAgent,
    ActiveAgentResponseStatus,
)
from retail.interfaces.jwt import JWTInterface


class ActiveAgentTest(TestCase):
    """Test cases for ActiveAgent service functionality."""

    def setUp(self):
        patcher = patch("weni_datalake_sdk.clients.client.send_commerce_webhook_data")
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

        self.mock_lambda_service = MagicMock()
        self.mock_jwt_generator = MagicMock(spec=JWTInterface)
        self.handler = ActiveAgent(
            lambda_service=self.mock_lambda_service,
            jwt_generator=self.mock_jwt_generator,
        )
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

        self.mock_jwt_generator.generate_jwt_token.return_value = "mock_jwt_token"

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
                "auth_token": "mock_jwt_token",
            },
        }

        self.handler.invoke(self.mock_agent, mock_data)

        self.mock_jwt_generator.generate_jwt_token.assert_called_once_with(
            str(self.mock_agent.project.uuid)
        )
        self.mock_lambda_service.invoke.assert_called_once_with(
            self.mock_agent.agent.lambda_arn, expected_payload
        )

    def test_invoke_lambda_with_jwt_generator(self):
        mock_data = MagicMock()
        mock_data.configure_mock(
            params={},
            payload={},
            credentials={},
            project_rules=[],
        )

        self.mock_jwt_generator.generate_jwt_token.return_value = "test_jwt_token"

        self.handler.invoke(self.mock_agent, mock_data)

        self.mock_jwt_generator.generate_jwt_token.assert_called_once_with(
            str(self.mock_agent.project.uuid)
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
        data = {"status": ActiveAgentResponseStatus.RULE_MATCHED}

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertTrue(result)

    def test_validate_response_rule_not_matched(self):
        data = {
            "status": ActiveAgentResponseStatus.RULE_NOT_MATCHED,
            "error": "No rule matched",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_pre_processing_failed(self):
        data = {
            "status": ActiveAgentResponseStatus.PRE_PROCESSING_FAILED,
            "error": "Pre-processing error",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_custom_rule_failed(self):
        data = {
            "status": ActiveAgentResponseStatus.CUSTOM_RULE_FAILED,
            "error": "Custom rule error",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_official_rule_failed(self):
        data = {
            "status": ActiveAgentResponseStatus.OFFICIAL_RULE_FAILED,
            "error": "Official rule error",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_global_rule_failed(self):
        data = {
            "status": ActiveAgentResponseStatus.GLOBAL_RULE_FAILED,
            "error": "Global rule error",
        }

        result = self.handler.validate_response(data, self.mock_agent)

        self.assertFalse(result)

    def test_validate_response_global_rule_not_matched(self):
        data = {
            "status": ActiveAgentResponseStatus.GLOBAL_RULE_NOT_MATCHED,
            "error": "Global rule not matched",
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
