"""Tests for retail wiring of ``weni_commons`` authentication."""

import jwt
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory
from weni_commons.auth import WeniAuthContext, WeniAuthUser

from retail.internal.authenticators import RetailAuthentication


class RetailAuthenticationTestCase(TestCase):
    """Validates the JWT path delegated to ``weni_commons``."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.auth = RetailAuthentication()
        self.mock_public_key = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"""
        self.sample_payload = {
            "project_uuid": "test-project-123",
            "module_source": "intelligent_agent",
            "exp": 9999999999,
            "iat": 1234567890,
        }

    @override_settings(JWT_PUBLIC_KEY=None)
    def test_missing_public_key_delegates_to_keycloak_backend(self):
        backend = MagicMock()
        backend.get_or_create_user.return_value = MagicMock()
        backend.verify_token.return_value = {"email": "kc@example.com"}
        auth = RetailAuthentication(oidc_backend=backend)

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer token"}

        _, auth_context = auth.authenticate(request)

        backend.get_or_create_user.assert_called_once()
        self.assertEqual(auth_context.token_type, "keycloak")
        self.assertEqual(auth_context.user_email, "kc@example.com")

    def test_missing_authorization_header_returns_none(self):
        with override_settings(JWT_PUBLIC_KEY=self.mock_public_key):
            request = self.factory.get("/")
            request.headers = {}

            self.assertIsNone(self.auth.authenticate(request))

    @patch("weni_commons.auth.authenticators.jwt.decode")
    @override_settings(JWT_PUBLIC_KEY=b"test-public-key")
    def test_authenticate_success_with_project_uuid(self, mock_jwt_decode):
        mock_jwt_decode.return_value = self.sample_payload

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer valid-token"}

        user, auth_context = self.auth.authenticate(request)

        self.assertIsInstance(user, WeniAuthUser)
        self.assertIsInstance(auth_context, WeniAuthContext)
        self.assertEqual(auth_context.project_uuid, "test-project-123")

    @patch("weni_commons.auth.authenticators.jwt.decode")
    @override_settings(JWT_PUBLIC_KEY=b"test-public-key")
    def test_authenticate_success_with_vtex_account(self, mock_jwt_decode):
        vtex_payload = {"vtex_account": "mystore", "exp": 9999999999}
        mock_jwt_decode.return_value = vtex_payload

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer valid-token"}

        _, auth_context = self.auth.authenticate(request)

        self.assertEqual(auth_context.vtex_account, "mystore")

    @patch("weni_commons.auth.authenticators.jwt.decode")
    @override_settings(JWT_PUBLIC_KEY=b"test-public-key")
    def test_authenticate_expired_token(self, mock_jwt_decode):
        mock_jwt_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer expired-token"}

        with self.assertRaises(AuthenticationFailed) as context:
            self.auth.authenticate(request)

        self.assertIn("Token expired", str(context.exception))
