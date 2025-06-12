from unittest.mock import MagicMock

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.flows.service import FlowsService


class TestFlowsService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = FlowsService(client=self.mock_client)
        self.user_email = "test@example.com"
        self.project_uuid = "project-uuid-123"
        self.payload = {"message": "test broadcast"}

    def test_init(self):
        service = FlowsService(client=self.mock_client)
        self.assertEqual(service.client, self.mock_client)

    def test_get_user_api_token_success(self):
        expected_response = {"token": "api-token-123", "expires_at": "2024-12-31"}
        self.mock_client.get_user_api_token.return_value = expected_response

        result = self.service.get_user_api_token(self.user_email, self.project_uuid)

        self.mock_client.get_user_api_token.assert_called_once_with(
            self.user_email, self.project_uuid
        )
        self.assertEqual(result, expected_response)

    def test_get_user_api_token_custom_api_exception(self):
        exception = CustomAPIException(status_code=404, detail="Not found")
        self.mock_client.get_user_api_token.side_effect = exception

        result = self.service.get_user_api_token(self.user_email, self.project_uuid)

        self.mock_client.get_user_api_token.assert_called_once_with(
            self.user_email, self.project_uuid
        )
        self.assertIsNone(result)

    def test_send_whatsapp_broadcast_success(self):
        mock_response = MagicMock()
        mock_response.status_code = 200
        self.mock_client.send_whatsapp_broadcast.return_value = mock_response

        result = self.service.send_whatsapp_broadcast(self.payload)

        self.mock_client.send_whatsapp_broadcast.assert_called_once_with(
            payload=self.payload
        )
        self.assertTrue(result)

    def test_send_whatsapp_broadcast_failure(self):
        mock_response = MagicMock()
        mock_response.status_code = 400
        self.mock_client.send_whatsapp_broadcast.return_value = mock_response

        result = self.service.send_whatsapp_broadcast(self.payload)

        self.mock_client.send_whatsapp_broadcast.assert_called_once_with(
            payload=self.payload
        )
        self.assertFalse(result)
