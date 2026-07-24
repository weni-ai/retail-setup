from unittest.mock import Mock

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.interfaces.services.connect import ConnectServiceInterface
from retail.services.connect.proxy import ConnectServiceProxy


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "connect-proxy-tests",
        }
    },
    CONNECT_USER_PERMISSIONS_CACHE_TTL=30,
)
class ConnectServiceProxyTest(TestCase):
    def setUp(self):
        cache.clear()
        self.mock_service = Mock(spec=ConnectServiceInterface)
        self.proxy = ConnectServiceProxy(connect_service=self.mock_service)

    def tearDown(self):
        cache.clear()

    def test_positive_authorization_is_cached(self):
        self.mock_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        first = self.proxy.get_user_permissions("project-uuid", "user@example.com")
        second = self.proxy.get_user_permissions("project-uuid", "user@example.com")

        self.assertEqual(first, (200, {"project_authorization": 2}))
        self.assertEqual(second, (200, {"project_authorization": 2}))
        self.mock_service.get_user_permissions.assert_called_once()

    def test_not_configured_level_is_not_cached(self):
        self.mock_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 0},
        )

        self.proxy.get_user_permissions("project-uuid", "user@example.com")
        self.proxy.get_user_permissions("project-uuid", "user@example.com")

        self.assertEqual(self.mock_service.get_user_permissions.call_count, 2)

    def test_non_200_response_is_not_cached(self):
        self.mock_service.get_user_permissions.return_value = (
            404,
            {"error": "User not found"},
        )

        self.proxy.get_user_permissions("project-uuid", "user@example.com")
        self.proxy.get_user_permissions("project-uuid", "user@example.com")

        self.assertEqual(self.mock_service.get_user_permissions.call_count, 2)

    def test_user_token_is_forwarded_to_service(self):
        self.mock_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        self.proxy.get_user_permissions("project-uuid", "user@example.com", "jwt-token")

        self.mock_service.get_user_permissions.assert_called_once_with(
            "project-uuid", "user@example.com", "jwt-token"
        )

    @override_settings(CONNECT_USER_PERMISSIONS_CACHE_TTL=0)
    def test_cache_disabled_when_ttl_is_zero(self):
        self.mock_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        self.proxy.get_user_permissions("project-uuid", "user@example.com")
        self.proxy.get_user_permissions("project-uuid", "user@example.com")

        self.assertEqual(self.mock_service.get_user_permissions.call_count, 2)
