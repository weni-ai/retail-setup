"""Tests for ``ConnectClient.send_data_export_email``.

The client only assembles the request; the network call and the
internal OIDC token are mocked so the test asserts the URL, method and
payload shape without touching Keycloak or Connect.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from retail.clients.connect.client import ConnectClient


@override_settings(CONNECT_REST_ENDPOINT="https://connect.example.com")
class ConnectClientSendDataExportEmailTests(TestCase):
    @patch("retail.clients.connect.client.InternalAuthentication")
    def test_posts_expected_url_and_payload(self, mock_auth_cls):
        mock_auth_cls.return_value.headers = {"Authorization": "Bearer token"}

        client = ConnectClient()
        response = MagicMock()
        response.json.return_value = {"sent": True}
        client.make_request = MagicMock(return_value=response)

        result = client.send_data_export_email(
            user_email="user@example.com",
            file_url="https://files/export.csv",
            start_date="2026-04-01",
            end_date="2026-05-01",
            template="all",
            status=["sent", "delivered"],
        )

        self.assertEqual(result, {"sent": True})
        client.make_request.assert_called_once_with(
            url="https://connect.example.com/v2/commerce/send-data-export-email/",
            method="POST",
            json={
                "user_email": "user@example.com",
                "file_url": "https://files/export.csv",
                "start_date": "2026-04-01",
                "end_date": "2026-05-01",
                "template": "all",
                "status": ["sent", "delivered"],
            },
            headers={"Authorization": "Bearer token"},
        )


@override_settings(CONNECT_REST_ENDPOINT="https://connect.example.com")
class ConnectClientLinkVtexAccountTests(TestCase):
    @patch("retail.clients.connect.client.InternalAuthentication")
    def test_posts_expected_url_and_payload(self, mock_auth_cls):
        mock_auth_cls.return_value.headers = {"Authorization": "Bearer token"}

        client = ConnectClient()
        response = MagicMock()
        response.json.return_value = {"success": True}
        client.make_request = MagicMock(return_value=response)

        result = client.link_vtex_account(
            project_uuid="project-uuid",
            vtex_account="mystore",
        )

        self.assertEqual(result, {"success": True})
        client.make_request.assert_called_once_with(
            url=(
                "https://connect.example.com/v2/commerce/projects/"
                "project-uuid/link-vtex-account/"
            ),
            method="POST",
            json={"vtex_account": "mystore"},
            headers={"Authorization": "Bearer token"},
        )
