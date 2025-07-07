from typing import Protocol, Tuple, Dict


class ConnectServiceInterface(Protocol):
    def get_user_permissions(
        self, project_uuid: str, user_email: str
    ) -> Tuple[int, Dict[str, str]]:
        ...
