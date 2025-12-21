"""
Tests for JWT authentication classes for inter-module communication.
"""

import jwt

from unittest.mock import patch
from django.test import TestCase

from rest_framework.test import APIRequestFactory
from rest_framework.exceptions import AuthenticationFailed

from retail.internal.jwt_authenticators import JWTModuleAuthentication


class JWTModuleAuthenticationTestCase(TestCase):
    """Test cases for JWTModuleAuthentication class for inter-module communication."""

    def setUp(self):
        """Set up test fixtures."""
        self.factory = APIRequestFactory()
        self.auth = JWTModuleAuthentication()

        # Mock JWT public key for testing
        self.mock_public_key = b"""-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA...
-----END PUBLIC KEY-----"""

        # Sample JWT payload for inter-module communication
        self.sample_payload = {
            "project_uuid": "test-project-123",
            "module_source": "intelligent_agent",
            "exp": 9999999999,  # Far future expiration
            "iat": 1234567890,
        }

    @patch("retail.internal.jwt_authenticators.settings")
    def test_authenticate_missing_public_key(self, mock_settings):
        """Test authentication fails when JWT_PUBLIC_KEY is not configured."""
        mock_settings.JWT_PUBLIC_KEY = None

        request = self.factory.get("/")
        request.headers = {}

        with self.assertRaises(AuthenticationFailed) as context:
            self.auth.authenticate(request)

        self.assertIn("JWT_PUBLIC_KEY not configured", str(context.exception))

    def test_authenticate_missing_authorization_header(self):
        """Test authentication fails when Authorization header is missing."""
        with patch("retail.internal.jwt_authenticators.settings") as mock_settings:
            mock_settings.JWT_PUBLIC_KEY = self.mock_public_key

            request = self.factory.get("/")
            request.headers = {}

            with self.assertRaises(AuthenticationFailed) as context:
                self.auth.authenticate(request)

            self.assertIn("Missing Authorization header", str(context.exception))

    def test_authenticate_invalid_token_format(self):
        """Test authentication fails when token is invalid (raw token without Bearer)."""
        with patch("retail.internal.jwt_authenticators.settings") as mock_settings:
            mock_settings.JWT_PUBLIC_KEY = self.mock_public_key

            request = self.factory.get("/")
            # Raw token (without Bearer) is now accepted, but will fail on decode
            request.headers = {"Authorization": "InvalidTokenValue"}

            with self.assertRaises(AuthenticationFailed) as context:
                self.auth.authenticate(request)

            self.assertIn("Invalid token", str(context.exception))

    @patch("retail.internal.jwt_authenticators.jwt.decode")
    @patch("retail.internal.jwt_authenticators.settings")
    def test_authenticate_missing_required_payload_fields(
        self, mock_settings, mock_jwt_decode
    ):
        """Test authentication fails when neither project_uuid nor vtex_account is in payload."""
        mock_settings.JWT_PUBLIC_KEY = self.mock_public_key
        mock_jwt_decode.return_value = {"some_other_field": "value"}

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer valid-token"}

        with self.assertRaises(AuthenticationFailed) as context:
            self.auth.authenticate(request)

        self.assertIn(
            "Token must contain 'project_uuid' or 'vtex_account'",
            str(context.exception),
        )

    @patch("retail.internal.jwt_authenticators.jwt.decode")
    @patch("retail.internal.jwt_authenticators.settings")
    def test_authenticate_success_with_project_uuid(
        self, mock_settings, mock_jwt_decode
    ):
        """Test successful authentication with project_uuid in payload."""
        mock_settings.JWT_PUBLIC_KEY = self.mock_public_key
        mock_jwt_decode.return_value = self.sample_payload

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer valid-token"}

        result = self.auth.authenticate(request)

        # Should return (None, None) as per DRF authentication contract
        self.assertEqual(result, (None, None))

        # Check that project_uuid and jwt_payload are attached to request
        self.assertEqual(request.project_uuid, "test-project-123")
        self.assertIsNone(request.vtex_account)
        self.assertEqual(request.jwt_payload, self.sample_payload)

    @patch("retail.internal.jwt_authenticators.jwt.decode")
    @patch("retail.internal.jwt_authenticators.settings")
    def test_authenticate_success_with_vtex_account(
        self, mock_settings, mock_jwt_decode
    ):
        """Test successful authentication with vtex_account in payload."""
        mock_settings.JWT_PUBLIC_KEY = self.mock_public_key
        vtex_payload = {"vtex_account": "mystore", "exp": 9999999999}
        mock_jwt_decode.return_value = vtex_payload

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer valid-token"}

        result = self.auth.authenticate(request)

        self.assertEqual(result, (None, None))
        self.assertIsNone(request.project_uuid)
        self.assertEqual(request.vtex_account, "mystore")
        self.assertEqual(request.jwt_payload, vtex_payload)

    @patch("retail.internal.jwt_authenticators.jwt.decode")
    @patch("retail.internal.jwt_authenticators.settings")
    def test_authenticate_expired_token(self, mock_settings, mock_jwt_decode):
        """Test authentication fails with expired token."""
        mock_settings.JWT_PUBLIC_KEY = self.mock_public_key
        mock_jwt_decode.side_effect = jwt.ExpiredSignatureError("Token expired")

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer expired-token"}

        with self.assertRaises(AuthenticationFailed) as context:
            self.auth.authenticate(request)

        self.assertIn("Token expired", str(context.exception))

    @patch("retail.internal.jwt_authenticators.jwt.decode")
    @patch("retail.internal.jwt_authenticators.settings")
    def test_authenticate_invalid_token(self, mock_settings, mock_jwt_decode):
        """Test authentication fails with invalid token."""
        mock_settings.JWT_PUBLIC_KEY = self.mock_public_key
        mock_jwt_decode.side_effect = jwt.InvalidTokenError("Invalid token")

        request = self.factory.get("/")
        request.headers = {"Authorization": "Bearer invalid-token"}

        with self.assertRaises(AuthenticationFailed) as context:
            self.auth.authenticate(request)

        self.assertIn("Invalid token", str(context.exception))

    def test_authenticate_verify_jwt_decode_called_correctly(self):
        """Test that jwt.decode is called with correct parameters."""
        with patch(
            "retail.internal.jwt_authenticators.jwt.decode"
        ) as mock_jwt_decode, patch(
            "retail.internal.jwt_authenticators.settings"
        ) as mock_settings:
            mock_settings.JWT_PUBLIC_KEY = self.mock_public_key
            mock_jwt_decode.return_value = self.sample_payload

            request = self.factory.get("/")
            request.headers = {"Authorization": "Bearer test-token"}

            self.auth.authenticate(request)

            # Verify jwt.decode was called with correct parameters
            mock_jwt_decode.assert_called_once_with(
                "test-token",
                self.mock_public_key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )
