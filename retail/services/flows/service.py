from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.flows.interface import FlowsClientInterface


class FlowsService:
    def __init__(self, client: FlowsClientInterface):
        self.client = client

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

    def send_whatsapp_broadcast(
        self, payload: dict, project_uuid: str, user_email: str
    ) -> dict:
        """
        Send a WhatsApp broadcast message.

        Args:
            payload (dict): The full body of the request as a pre-built payload.
            project_uuid (str): The UUID of the project.
            user_email (str): Email of the user for authentication.

        Returns:
            dict: API response from the Flows service.
        """
        # Retrieve the API token
        token = self.client.get_user_api_token(user_email, project_uuid)
        if not token:
            raise CustomAPIException("Failed to retrieve API token.")

        # Send the broadcast using the token
        return self.client.send_whatsapp_broadcast(payload=payload, token=token)
