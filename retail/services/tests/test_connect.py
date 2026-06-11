from unittest.mock import Mock
from django.test import TestCase

from retail.services.connect.service import ConnectService
from retail.interfaces.clients.connect.interface import ConnectClientInterface


class ConnectServiceTest(TestCase):
    def setUp(self):
        self.mock_client = Mock(spec=ConnectClientInterface)
        self.service = ConnectService(connect_client=self.mock_client)

    def test_get_user_permissions_without_token(self):
        """Test get_user_permissions without user token (internal user flow)"""
        self.mock_client.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        result = self.service.get_user_permissions("project-uuid", "user@example.com")

        self.assertEqual(result, (200, {"project_authorization": 2}))
        self.mock_client.get_user_permissions.assert_called_once_with(
            "project-uuid", "user@example.com", None
        )

    def test_get_user_permissions_with_token(self):
        """Test get_user_permissions with user token (regular user flow)"""
        self.mock_client.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        result = self.service.get_user_permissions(
            "project-uuid", "user@example.com", "jwt-token"
        )

        self.assertEqual(result, (200, {"project_authorization": 3}))
        self.mock_client.get_user_permissions.assert_called_once_with(
            "project-uuid", "user@example.com", "jwt-token"
        )

    def test_get_user_permissions_error_response(self):
        """Test get_user_permissions with error response"""
        self.mock_client.get_user_permissions.return_value = (
            404,
            {"error": "User not found"},
        )

        result = self.service.get_user_permissions("project-uuid", "user@example.com")

        self.assertEqual(result, (404, {"error": "User not found"}))

    def test_send_data_export_email_delegates_to_client(self):
        """send_data_export_email forwards every field to the client."""
        self.mock_client.send_data_export_email.return_value = {"sent": True}

        result = self.service.send_data_export_email(
            user_email="user@example.com",
            file_url="https://files/export.csv",
            start_date="2026-04-01",
            end_date="2026-05-01",
            template="all",
            status=["sent", "delivered"],
        )

        self.assertEqual(result, {"sent": True})
        self.mock_client.send_data_export_email.assert_called_once_with(
            user_email="user@example.com",
            file_url="https://files/export.csv",
            start_date="2026-04-01",
            end_date="2026-05-01",
            template="all",
            status=["sent", "delivered"],
        )

    def test_send_data_export_email_returns_none_on_client_error(self):
        """A client failure is swallowed so the export task never crashes."""
        self.mock_client.send_data_export_email.side_effect = RuntimeError("boom")

        result = self.service.send_data_export_email(
            user_email="user@example.com",
            file_url="https://files/export.csv",
            start_date="2026-04-01",
            end_date="2026-05-01",
            template="all",
            status=["sent"],
        )

        self.assertIsNone(result)

    def test_send_contract_acceptance_email_delegates_to_client(self):
        """send_contract_acceptance_email forwards every field to the client."""
        self.mock_client.send_contract_acceptance_email.return_value = {"sent": True}

        result = self.service.send_contract_acceptance_email(
            user_email="user@example.com",
            acceptance_id="acceptance-uuid",
            subject="Your contract",
            body_html="<p>Hello</p>",
            file_name="contract-v2.1.pdf",
            file_base64="JVBERi0=",
        )

        self.assertEqual(result, {"sent": True})
        self.mock_client.send_contract_acceptance_email.assert_called_once_with(
            user_email="user@example.com",
            acceptance_id="acceptance-uuid",
            subject="Your contract",
            body_html="<p>Hello</p>",
            file_name="contract-v2.1.pdf",
            file_base64="JVBERi0=",
        )

    def test_send_contract_acceptance_email_returns_none_on_client_error(self):
        """A client failure is swallowed so the email task never crashes."""
        self.mock_client.send_contract_acceptance_email.side_effect = RuntimeError(
            "boom"
        )

        result = self.service.send_contract_acceptance_email(
            user_email="user@example.com",
            acceptance_id="acceptance-uuid",
            subject="Your contract",
            body_html="<p>Hello</p>",
            file_name="contract-v2.1.pdf",
            file_base64="JVBERi0=",
        )

        self.assertIsNone(result)

    def test_default_connect_client_initialization(self):
        """Test that ConnectService initializes with default ConnectClient when none provided"""
        service = ConnectService()

        self.assertIsNotNone(service.connect_client)

    def test_custom_connect_client_initialization(self):
        """Test that ConnectService uses provided ConnectClient"""
        custom_client = Mock(spec=ConnectClientInterface)
        service = ConnectService(connect_client=custom_client)

        self.assertEqual(service.connect_client, custom_client)
