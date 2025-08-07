from typing import Protocol, Dict, Tuple, Optional


class ConnectClientInterface(Protocol):
    def get_user_permissions(
        self, project_uuid: str, user_email: str, user_token: Optional[str] = None
    ) -> Tuple[int, Dict[str, str]]: ...
