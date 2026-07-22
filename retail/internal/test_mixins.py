from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

from django.test import override_settings
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth.models import Permission

from weni_commons.auth import WeniAuthContext, WeniAuthUser

User = get_user_model()

CONNECT_SERVICE_PROXY_PATH = "retail.internal.permissions.ConnectServiceProxy"
RETAIL_AUTH_PATH = "retail.internal.authenticators.RetailAuthentication.authenticate"

TEST_CACHE_SETTINGS = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "unique-test-cache",
        "OPTIONS": {
            "MAX_ENTRIES": 1000,
            "CULL_FREQUENCY": 3,
        },
    }
}

TEST_SETTINGS_OVERRIDES = {
    "CACHES": TEST_CACHE_SETTINGS,
    "CELERY_TASK_ALWAYS_EAGER": True,
    "CELERY_BROKER_URL": "memory://",
    "CELERY_RESULT_BACKEND": "cache+memory://",
    "CONNECT_REST_ENDPOINT": "http://test-connect.local",
    "INTEGRATIONS_REST_ENDPOINT": "http://test-integrations.local",
    "FLOWS_REST_ENDPOINT": "http://test-flows.local",
    "NEXUS_REST_ENDPOINT": "http://test-nexus.local",
    "CODE_ACTIONS_REST_ENDPOINT": "http://test-code-actions.local",
    "USE_LAMBDA": False,
    "USE_S3": False,
    "USE_META": False,
    "DOMAIN": "http://test.local",
    "REDIS_URL": "redis://test.local:6379",
}


class BaseTestMixin:
    """
    Mixin for tests that need to mock the ConnectServiceProxy.

    Provides standardized configuration for:
    - ConnectServiceProxy mock
    - In-memory cache configuration (overrides Redis)
    - Test endpoint configurations (prevents empty URL errors)
    - User permissions configuration
    - Helper methods for different test scenarios

    Usage:
        class MyViewTest(BaseTestMixin, APITestCase):
            def setUp(self):
                super().setUp()
                # Your specific setup here

            def test_something(self):
                self.setup_connect_service_mock(
                    status_code=200,
                    permissions={"project_authorization": 2}
                )
                # Your test here
    """

    def setUp(self):
        """Base setup for tests with cache configuration"""
        super().setUp()
        self._connect_service_patcher = None
        self._mock_connect_service = None
        self._mock_connect_instance = None

        self._setup_test_cache()

    def tearDown(self):
        """Cleanup patches and cache"""
        if self._connect_service_patcher:
            self._connect_service_patcher.stop()

        self._cleanup_test_cache()
        super().tearDown()

    def _setup_test_cache(self):
        """Configure in-memory cache for testing"""
        from django.core.cache import cache

        cache.clear()

    def _cleanup_test_cache(self):
        """Clean up test cache after each test"""
        from django.core.cache import cache

        cache.clear()

    def setup_connect_service_mock(
        self,
        status_code: int = 200,
        permissions: Optional[Dict[str, Any]] = None,
        auto_start: bool = True,
    ) -> MagicMock:
        """
        Configure the ConnectServiceProxy mock.

        Args:
            status_code: Service response status code
            permissions: Permissions dictionary returned
            auto_start: Whether to start the patch automatically

        Returns:
            Mock instance of ConnectService for additional configurations
        """
        if permissions is None:
            permissions = {"project_authorization": 2}

        self._connect_service_patcher = patch(CONNECT_SERVICE_PROXY_PATH)

        if auto_start:
            self._mock_connect_service = self._connect_service_patcher.start()
        else:
            self._mock_connect_service = self._connect_service_patcher

        self._mock_connect_instance = self._mock_connect_service.return_value
        self._mock_connect_instance.get_user_permissions.return_value = (
            status_code,
            permissions,
        )

        return self._mock_connect_instance

    def setup_internal_user_permissions(self, user: User) -> None:
        """
        Add internal communication permission to user.

        Args:
            user: User to add the permission to
        """
        content_type = ContentType.objects.get_for_model(User)
        permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="Can Communicate Internally",
            content_type=content_type,
        )
        user.user_permissions.add(permission)
        user.save()

    def clear_test_cache(self):
        """
        Manually clear the test cache during a test.
        Useful for testing cache behavior.
        """
        from django.core.cache import cache

        cache.clear()

    def get_cache_value(self, key: str):
        """
        Helper method to get cache value during tests.

        Args:
            key: Cache key to retrieve

        Returns:
            Cached value or None if not found
        """
        from django.core.cache import cache

        return cache.get(key)

    def set_cache_value(self, key: str, value, timeout: Optional[int] = None):
        """
        Helper method to set cache value during tests.

        Args:
            key: Cache key
            value: Value to cache
            timeout: Cache timeout in seconds
        """
        from django.core.cache import cache

        cache.set(key, value, timeout=timeout)


def patch_retail_auth(
    *,
    project_uuid: Optional[str] = None,
    vtex_account: Optional[str] = None,
    user_email: Optional[str] = None,
    account_id: Optional[str] = None,
    is_internal: bool = False,
    token_type: str = "jwt",
):
    """Patch unified retail authentication for view/integration tests.

    Args:
        project_uuid: Project UUID placed on the auth context.
        vtex_account: VTEX account name placed on the auth context.
        user_email: User email placed on the auth context.
        account_id: Optional account identity claim placed on the auth context.
        is_internal: Whether the request is marked as internal.
        token_type: ``jwt`` or ``keycloak``.

    Returns:
        A ``unittest.mock.patch`` context for ``RetailAuthentication.authenticate``.
    """

    auth_context = WeniAuthContext(
        project_uuid=project_uuid,
        vtex_account=vtex_account,
        user_email=user_email,
        account_id=account_id,
        is_internal=is_internal,
        token_type=token_type,
    )
    return patch(
        RETAIL_AUTH_PATH,
        return_value=(WeniAuthUser(email=user_email), auth_context),
    )


def patch_keycloak_auth_bypass(user: Optional[Any] = None):
    """Patch retail authentication for views that only need a user principal.

    Args:
        user: Optional Django user principal returned by the authenticator.

    Returns:
        A ``unittest.mock.patch`` context for ``RetailAuthentication.authenticate``.
    """

    auth_context = WeniAuthContext(user_email="test@example.com", token_type="keycloak")
    return patch(
        RETAIL_AUTH_PATH,
        return_value=(user or MagicMock(), auth_context),
    )


def with_test_settings(test_class):
    """
    Class decorator to apply comprehensive test settings automatically.

    Usage:
        @with_test_settings
        class MyTestClass(ConnectServiceTestMixin, APITestCase):
            pass
    """
    return override_settings(**TEST_SETTINGS_OVERRIDES)(test_class)


class ConnectServicePermissionScenarios:
    """
    Class with common permission scenarios for reuse in tests.
    """

    CONTRIBUTOR_PERMISSIONS = {"project_authorization": 2}
    MODERATOR_PERMISSIONS = {"project_authorization": 3}
    CHAT_USER_PERMISSIONS = {"project_authorization": 5}
    NO_PERMISSIONS = {"project_authorization": 1}
    USER_NOT_FOUND = (404, {"error": "User not found"})
    UNAUTHORIZED = (401, {"error": "Unauthorized"})
    FORBIDDEN = (403, {"error": "Forbidden"})
    INTERNAL_ERROR = (500, {"error": "Internal server error"})

    @classmethod
    def success_scenario(cls, permission_level: int = 2) -> tuple:
        """Success scenario with specific permission level"""
        return (200, {"project_authorization": permission_level})

    @classmethod
    def error_scenario(cls, status_code: int, message: str) -> tuple:
        """Custom error scenario"""
        return (status_code, {"error": message})


class CacheTestMixin:
    """
    Additional mixin specifically for cache-related testing functionality.
    Can be used separately or combined with ConnectServiceTestMixin.
    """

    def assert_cache_hit(self, key: str, expected_value=None):
        """
        Assert that a cache key exists and optionally check its value.

        Args:
            key: Cache key to check
            expected_value: Expected cached value (optional)
        """
        from django.core.cache import cache

        cached_value = cache.get(key)

        self.assertIsNotNone(
            cached_value, f"Expected cache key '{key}' to exist, but it was not found"
        )

        if expected_value is not None:
            self.assertEqual(
                cached_value,
                expected_value,
                f"Cache value for key '{key}' does not match expected value",
            )

    def assert_cache_miss(self, key: str):
        """
        Assert that a cache key does not exist.

        Args:
            key: Cache key to check
        """
        from django.core.cache import cache

        cached_value = cache.get(key)

        self.assertIsNone(
            cached_value,
            f"Expected cache key '{key}' to not exist, but found: {cached_value}",
        )

    def assert_cache_timeout(self, key: str, value, timeout: int):
        """
        Assert that a cache entry was set with the correct timeout.
        Note: This is a helper for testing cache behavior,
        actual timeout testing requires time manipulation.

        Args:
            key: Cache key
            value: Expected value
            timeout: Expected timeout
        """
        from django.core.cache import cache

        cache.set(key, value, timeout=timeout)

        self.assert_cache_hit(key, value)
