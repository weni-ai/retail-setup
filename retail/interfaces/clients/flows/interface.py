from abc import ABC, abstractmethod
from typing import List, Optional, Dict


class FlowsClientInterface(ABC):
    @abstractmethod
    def get_user_api_token(self, user_email: str, project_uuid: str):
        """
        Retrieve the user API token for a given email and project UUID.
        """
        pass

    @abstractmethod
    def send_whatsapp_broadcast(self, payload: Dict) -> Dict:
        """
        Sends a WhatsApp broadcast message.

        Args:
            payload (dict): The pre-built payload containing all necessary data for the broadcast.

        Returns:
            dict: API response containing the broadcast information.
        """
        pass
