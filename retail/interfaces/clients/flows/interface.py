from abc import ABC, abstractmethod
from typing import Dict, List


class FlowsClientInterface(ABC):
    @abstractmethod
    def get_user_api_token(self, user_email: str, project_uuid: str):
        """
        Retrieve the user API token for a given email and project UUID.
        """
        pass

    @abstractmethod
    def send_whatsapp_broadcast(self, payload: Dict, jwt_token: str) -> Dict:
        """
        Sends a WhatsApp broadcast message.

        Args:
            payload (dict): The pre-built payload containing all necessary data for the broadcast.
            jwt_token (str): JWT token for authentication.
        Returns:
            Response: API response containing the broadcast information.
        """
        pass

    @abstractmethod
    def get_contact_groups(self, project_uuid: str, name: str) -> dict:
        """List Flows contact groups filtered by name for a project."""
        pass

    @abstractmethod
    def create_contact_group(self, project_uuid: str, name: str) -> dict:
        """Create a Flows contact group for a project."""
        pass

    @abstractmethod
    def create_contact(
        self, project_uuid: str, name: str, urns: List[str], groups: List[str]
    ) -> dict:
        """POST /api/v2/contacts.json already assigned to the given groups."""
        pass

    @abstractmethod
    def add_contact_to_group(
        self, project_uuid: str, contacts: List[str], group: str
    ) -> dict:
        """POST /api/v2/contact_actions.json to add contacts to a group."""
        pass
