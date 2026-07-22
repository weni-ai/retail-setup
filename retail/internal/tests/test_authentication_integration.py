"""Integration tests for retail authentication wiring."""

import jwt
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIRequestFactory
from weni_commons.auth import WeniAuthUser

from retail.internal.authenticators import RetailAuthentication
from weni_commons.auth import (
    get_project_uuid,
    get_user_email,
    get_vtex_account,
    is_internal_request,
)
from retail.internal.tests.test_oidc_backend import TestOIDCAuthenticationBackend

User = get_user_model()


@override_settings(
    JWT_PUBLIC_KEY=b"test-public-key",
    OIDC_DRF_AUTH_BACKEND="retail.internal.tests.test_oidc_backend.TestOIDCAuthenticationBackend",
)
class RetailAuthenticationIntegrationTestCase(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.auth = RetailAuthentication()
        self.user = User.objects.create_user(
            username="retail-user",
            email="user@example.com",
            password="password",
        )
        TestOIDCAuthenticationBackend.user = self.user
        TestOIDCAuthenticationBackend.claims = {
            "email": "user@example.com",
            "project_uuid": "keycloak-project",
            "vtex_account": "keycloak-store",
        }
        TestOIDCAuthenticationBackend.should_fail = False

    def _request_with_bearer(self, token: str):
        request = self.factory.get("/")
        request.headers = {"Authorization": f"Bearer {token}"}
        return request

    @patch("weni_commons.auth.authenticators.jwt.decode")
    def test_app_io_jwt_populates_request_auth(self, mock_jwt_decode):
        mock_jwt_decode.return_value = {
            "project_uuid": "project-from-app-io",
            "vtex_account": "store-from-app-io",
            "user_email": "appio@example.com",
        }

        request = self._request_with_bearer("app-io-token")
        user, auth_context = self.auth.authenticate(request)

        self.assertIsInstance(user, WeniAuthUser)
        request.user = user
        request.auth = auth_context
        self.assertEqual(get_project_uuid(request), "project-from-app-io")
        self.assertEqual(get_vtex_account(request), "store-from-app-io")
        self.assertEqual(get_user_email(request), "appio@example.com")
        self.assertFalse(is_internal_request(request))

    @patch("weni_commons.auth.authenticators.jwt.decode")
    def test_keycloak_fallback_when_token_is_not_app_io_jwt(self, mock_jwt_decode):
        mock_jwt_decode.side_effect = jwt.InvalidTokenError("not our jwt")

        auth = RetailAuthentication(oidc_backend=TestOIDCAuthenticationBackend())
        user, auth_context = auth.authenticate(
            self._request_with_bearer("keycloak-token")
        )

        self.assertEqual(user, self.user)
        self.assertEqual(auth_context.token_type, "keycloak")

    @patch("weni_commons.auth.authenticators.jwt.decode")
    def test_expired_app_io_jwt_does_not_fallback_to_keycloak(self, mock_jwt_decode):
        mock_jwt_decode.side_effect = jwt.ExpiredSignatureError("expired")

        with self.assertRaises(AuthenticationFailed):
            self.auth.authenticate(self._request_with_bearer("expired-token"))

    def test_injected_oidc_backend_is_used_for_keycloak_path(self):
        backend = MagicMock()
        backend.get_or_create_user.return_value = self.user
        backend.verify_token.return_value = {"email": "injected@example.com"}

        auth = RetailAuthentication(oidc_backend=backend)

        with override_settings(JWT_PUBLIC_KEY=None):
            _, auth_context = auth.authenticate(self._request_with_bearer("token"))

        backend.get_or_create_user.assert_called_once()
        self.assertEqual(auth_context.user_email, "injected@example.com")
