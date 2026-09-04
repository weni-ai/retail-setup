import logging
from typing import Callable, Optional

from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.flows.interface import FlowsClientInterface
from retail.clients.flows.client import FlowsClient


logger = logging.getLogger(__name__)


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

    def send_whatsapp_broadcast(self, payload: dict) -> dict:
        """
        Send a WhatsApp broadcast message.

        Args:
            payload (dict): The full body of the request as a pre-built payload.
            project_uuid (str): The UUID of the project.

        Returns:
            dict: API response from the Flows service.
        """
        return self.client.send_whatsapp_broadcast(payload=payload)

    def send_purchase_event(self, payload: dict, jwt_token: str) -> dict:
        """
        Send a purchase event to the Flows service using JWT authentication.

        Args:
            payload (dict): The purchase event data to send.
            jwt_token (str): JWT token for authentication.

        Returns:
            dict: API response from the Flows service.
        """
        return self.client.send_purchase_event(payload=payload, jwt_token=jwt_token)

    def get_contact_groups(self, project_uuid: str, name: str) -> Optional[dict]:
        """Return Flows groups matching ``name``, or ``None`` on infra failure."""
        return self._call_contact_group_client(
            "list",
            self.client.get_contact_groups,
            project_uuid=project_uuid,
            name=name,
        )

    def create_contact_group(self, project_uuid: str, name: str) -> Optional[dict]:
        """Create a Flows contact group, or ``None`` on infra failure."""
        return self._call_contact_group_client(
            "create",
            self.client.create_contact_group,
            project_uuid=project_uuid,
            name=name,
        )

    def _call_contact_group_client(
        self,
        action: str,
        client_method: Callable[..., dict],
        project_uuid: str,
        name: str,
    ) -> Optional[dict]:
        try:
            return client_method(project_uuid=project_uuid, name=name)
        except CustomAPIException as exc:
            logger.error(
                f"Failed to {action} Flows contact group for "
                f"project={project_uuid} name={name}: status={exc.status_code}"
            )
            return None
        except Exception as exc:
            logger.exception(
                f"Failed to {action} Flows contact group for "
                f"project={project_uuid} name={name}: {exc}"
            )
            return None
