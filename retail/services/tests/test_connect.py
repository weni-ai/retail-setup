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

    def test_default_connect_client_initialization(self):
        """Test that ConnectService initializes with default ConnectClient when none provided"""
        service = ConnectService()

        self.assertIsNotNone(service.connect_client)

    def test_custom_connect_client_initialization(self):
        """Test that ConnectService uses provided ConnectClient"""
        custom_client = Mock(spec=ConnectClientInterface)
        service = ConnectService(connect_client=custom_client)

        self.assertEqual(service.connect_client, custom_client)
