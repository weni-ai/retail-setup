from typing import Optional, Tuple, Dict

from django.core.cache import cache

from retail.interfaces.services.connect import ConnectServiceInterface
from retail.services.connect import ConnectService

CACHE_KEY_PREFIX = "connect_user_permissions"


class ConnectServiceProxy(ConnectServiceInterface):
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

        if status == 200:
            cache.set(cache_key, permissions, timeout=60)

        return status, permissions
