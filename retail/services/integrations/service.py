from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface


class IntegrationsService:
    def __init__(self, client: IntegrationsClientInterface):
        self.client = client

    def get_vtex_integration_detail(self, project_uuid: str) -> dict:
        """
        Retrieve the VTEX integration details for a given project UUID.
        Handles communication errors and returns None in case of failure.
        """
        try:
            return self.client.get_vtex_integration_detail(project_uuid)
        except CustomAPIException as e:
            print(f"Error {e.status_code} when retrieving VTEX integration for project {project_uuid}.")
            return None
