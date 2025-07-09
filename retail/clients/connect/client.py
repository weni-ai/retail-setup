from django.conf import settings

from retail.interfaces.clients.connect.interface import (
    ConnectClientInterface,
)
from retail.clients.base import RequestClient, InternalAuthentication


class ConnectClient(RequestClient, ConnectClientInterface):
    def __init__(self):
        self.base_url = settings.CONNECT_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def get_user_permissions(self, project_uuid, user_email):
        url = f"{self.base_url}/v2/projects/{project_uuid}/authorization"
        params = {"user": user_email}

        response = self.make_request(
            url=url,
            method="GET",
            headers=self.authentication_instance.headers,
            params=params,
        )

        return response.status_code, response.json()
