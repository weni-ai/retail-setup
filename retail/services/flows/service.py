from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.flows.interface import FlowsClientInterface


class FlowsService:
    def __init__(self, client: FlowsClientInterface):
        self.client = client

    def get_user_api_token(self, user_email: str, project_uuid: str) -> dict:
        """
        Retrieve the user API token for a given email and project UUID.
        Handles communication errors and returns None in case of failure.
        """
        try:
            return self.client.get_user_api_token(user_email, project_uuid)
        except CustomAPIException as e:
            print(f"Error {e.status_code} when retrieving user API token for project {project_uuid}.")
            return None
