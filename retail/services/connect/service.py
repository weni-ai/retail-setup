from typing import Optional

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
