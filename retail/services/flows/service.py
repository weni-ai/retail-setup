from typing import Optional

from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.flows.interface import FlowsClientInterface
from retail.clients.flows.client import FlowsClient


class FlowsService:
    def __init__(self, client: Optional[FlowsClientInterface] = None):
        self.client = client or FlowsClient()

    def get_user_api_token(self, user_email: str, project_uuid: str) -> dict:
        """
        Retrieve the user API token for a given email and project UUID.
        """
        try:
            return self.client.get_user_api_token(user_email, project_uuid)
        except CustomAPIException as e:
            print(
                f"Error {e.status_code} when retrieving user API token for project {project_uuid}."
            )
            return None

    def send_whatsapp_broadcast(self, payload: dict) -> bool:
        """
        Send a WhatsApp broadcast message.

        Args:
            payload (dict): The full body of the request as a pre-built payload.
            project_uuid (str): The UUID of the project.

        Returns:
            dict: API response from the Flows service.
        """
        return self.client.send_whatsapp_broadcast(payload=payload)

    def send_purchase_event(self, payload: dict) -> dict:
        """
        Send a purchase event to the Flows service.
        """
        return self.client.send_purchase_event(payload=payload)
