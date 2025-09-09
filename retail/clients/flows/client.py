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

    def send_whatsapp_broadcast(self, payload: dict) -> dict:
        """
        Sends a WhatsApp broadcast message using the Flows API.

        Args:
            payload (dict): The full body of the request as a pre-built payload.

        Returns:
            dict: Response from the API.
        """

        url = f"{self.base_url}/api/v2/internals/whatsapp_broadcasts"

        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=self.authentication_instance.headers,
        )
        return response.json()

    def send_purchase_event(self, payload: dict, jwt_token: str) -> dict:
        """
        Send a purchase event to the Flows API using JWT authentication.

        Args:
            payload (dict): The purchase event data to send.
            jwt_token (str): JWT token for authentication.

        Returns:
            dict: Response from the API.
        """
        url = f"{self.base_url}/conversion/"

        # Create headers with Bearer token
        headers = {
            "Authorization": f"Bearer {jwt_token}",
            "Content-Type": "application/json",
        }

        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=headers,
        )
        return response
