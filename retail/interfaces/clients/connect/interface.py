from typing import Protocol, Dict, Tuple


class ConnectClientInterface(Protocol):
    def get_user_permissions(
        self, project_uuid: str, user_email: str
    ) -> Tuple[int, Dict[str, str]]:
        ...
