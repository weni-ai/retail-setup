from typing import Dict, Optional, Tuple

from django.conf import settings
from django.core.cache import cache

from retail.interfaces.services.connect import ConnectServiceInterface
from retail.services.connect import ConnectService

CACHE_KEY_PREFIX = "connect_user_permissions"

# ``not_configured`` level returned by Connect when the user has no
# authorization on the project yet. It must never be cached: a permission
# created moments earlier could otherwise be masked by a stale negative and
# yield a false 403 until the entry expired.
NOT_CONFIGURED_LEVEL = 0


class ConnectServiceProxy(ConnectServiceInterface):
    """Caching decorator over the external Connect authorization lookup.

    Only positive authorizations are cached, for a short TTL, so the
    hot path avoids repeated external GETs while a freshly granted
    permission is never blocked by a cached negative result.
    """

    def __init__(self, connect_service: Optional[ConnectServiceInterface] = None):
        self.connect_service = connect_service or ConnectService()

    def get_user_permissions(
        self, project_uuid: str, user_email: str, user_token: Optional[str] = None
    ) -> Tuple[int, Dict[str, str]]:
        cache_key = f"{CACHE_KEY_PREFIX}_{project_uuid}_{user_email}"

        cached_permissions = cache.get(cache_key)
        if cached_permissions:
            return 200, cached_permissions

        status, permissions = self.connect_service.get_user_permissions(
            project_uuid, user_email, user_token
        )

        if self._should_cache(status, permissions):
            cache.set(
                cache_key,
                permissions,
                timeout=settings.CONNECT_USER_PERMISSIONS_CACHE_TTL,
            )

        return status, permissions

    def _should_cache(self, status: int, permissions: Dict[str, str]) -> bool:
        """Return whether the Connect response is a cacheable positive result.

        Args:
            status: HTTP status returned by Connect.
            permissions: The decoded Connect payload.

        Returns:
            ``True`` only when the caching is enabled, the lookup
            succeeded and the user holds an existing authorization level
            (anything other than ``not_configured``).
        """
        if settings.CONNECT_USER_PERMISSIONS_CACHE_TTL <= 0:
            return False

        if status != 200:
            return False

        return permissions.get("project_authorization") != NOT_CONFIGURED_LEVEL
