"""Client for connection with flows"""

from django.conf import settings

from retail.clients.base import RequestClient, InternalAuthentication
from retail.interfaces.clients.flows.interface import FlowsClientInterface


class FlowsClient(RequestClient, FlowsClientInterface):
    def __init__(self):
        self.base_url = settings.FLOWS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def get_user_api_token(self, user_email: str, project_uuid: str):
        """
        Fetch a user API token from the Flows service.

        Args:
            user_email (str): Email of the user.
            project_uuid (str): UUID of the project.

        Returns:
            str: API token for the user.
        """
        url = f"{self.base_url}/api/v2/internals/users/api-token/"
        params = dict(user=user_email, project=str(project_uuid))
        response = self.make_request(
            url,
            method="GET",
            params=params,
            headers=self.authentication_instance.headers,
        )
        return response.json()

    def send_whatsapp_broadcast(self, payload: dict, token: str) -> dict:
        """
        Sends a WhatsApp broadcast message using the Flows API.

        Args:
            payload (dict): The full body of the request as a pre-built payload.
            token (str): Authorization token for the API.

        Returns:
            dict: Response from the API.
        """
        if not token:
            raise ValueError("Authorization token is required to send a broadcast.")

        url = f"{self.base_url}/api/v2/whatsapp_broadcasts.json"
        headers = {
            "Authorization": f"Token {token}",
            "Content-Type": "application/json",
        }

        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=headers,
        )
        return response.json()
