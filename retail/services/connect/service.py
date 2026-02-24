from typing import Dict, Optional

from retail.interfaces.clients.connect.interface import ConnectClientInterface
from retail.interfaces.services.connect import ConnectServiceInterface
from retail.clients.connect.client import ConnectClient


class ConnectService(ConnectServiceInterface):
    def __init__(self, connect_client: Optional[ConnectClientInterface] = None):
        self.connect_client = connect_client or ConnectClient()

    def get_user_permissions(
        self, project_uuid, user_email, user_token: Optional[str] = None
    ):
        return self.connect_client.get_user_permissions(
            project_uuid, user_email, user_token
        )

    def create_vtex_project(
        self,
        user_email: str,
        vtex_account: str,
        language: str,
        organization_name: str,
        project_name: str,
    ) -> Dict:
        return self.connect_client.create_vtex_project(
            user_email=user_email,
            vtex_account=vtex_account,
            language=language,
            organization_name=organization_name,
            project_name=project_name,
        )
