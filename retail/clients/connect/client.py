from typing import Optional
from django.conf import settings

from retail.interfaces.clients.connect.interface import (
    ConnectClientInterface,
)
from retail.clients.base import (
    RequestClient,
    InternalAuthentication,
    UserAuthentication,
)


class ConnectClient(RequestClient, ConnectClientInterface):
    def __init__(self):
        self.base_url = settings.CONNECT_REST_ENDPOINT
        self.internal_authentication = InternalAuthentication()

    def get_user_permissions(
        self, project_uuid, user_email, user_token: Optional[str] = None
    ):
        url = f"{self.base_url}/v2/projects/{project_uuid}/authorization"

        if user_token:
            auth_instance = UserAuthentication(user_token)
            params = {}
        else:
            auth_instance = self.internal_authentication
            params = {"user": user_email}

        response = self.make_request(
            url=url,
            method="GET",
            headers=auth_instance.headers,
            params=params,
        )

        return response.status_code, response.json()
