from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from retail.clients.exceptions import CustomAPIException


def _auth_bypass():
    """Patches InternalOIDCAuthentication to always authenticate."""

    return patch(
        "retail.internal.authenticators.InternalOIDCAuthentication.authenticate",
        return_value=(MagicMock(is_authenticated=True), None),
    )


class TestCreateProjectUserView(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.url = "/vtex/account/mystore/project-user/"

    @_auth_bypass()
    @patch("retail.vtex.views.CreateProjectUserUseCase")
    def test_returns_200_with_connect_response(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {
            "project_uuid": "abc-123",
            "user_uuid": "user-456",
        }

        response = self.client.post(
            self.url,
            {"user_email": "user@vtex.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["project_uuid"], "abc-123")
        self.assertEqual(data["user_uuid"], "user-456")

    @_auth_bypass()
    @patch("retail.vtex.views.CreateProjectUserUseCase")
    def test_passes_correct_dto(self, mock_cls, _auth):
        mock_cls.return_value.execute.return_value = {}

        self.client.post(
            self.url,
            {"user_email": "user@vtex.com"},
            format="json",
        )

        call_args = mock_cls.return_value.execute.call_args
        dto = call_args[0][0]
        self.assertEqual(dto.vtex_account, "mystore")
        self.assertEqual(dto.user_email, "user@vtex.com")

    @_auth_bypass()
    def test_returns_400_when_email_missing(self, _auth):
        response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, 400)

    @_auth_bypass()
    def test_returns_400_for_invalid_email(self, _auth):
        response = self.client.post(
            self.url,
            {"user_email": "not-an-email"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)

    @_auth_bypass()
    @patch("retail.vtex.views.CreateProjectUserUseCase")
    def test_returns_502_when_connect_fails(self, mock_cls, _auth):
        mock_cls.return_value.execute.side_effect = CustomAPIException(
            detail="Connect unavailable", status_code=502
        )

        response = self.client.post(
            self.url,
            {"user_email": "user@vtex.com"},
            format="json",
        )

        self.assertEqual(response.status_code, 502)

    def test_returns_401_without_auth(self):
        response = self.client.post(
            self.url,
            {"user_email": "user@vtex.com"},
            format="json",
        )

        self.assertIn(response.status_code, [401, 403])
