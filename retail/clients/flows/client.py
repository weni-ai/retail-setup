"""Client for connection with flows"""

from typing import Dict, List, Optional

from django.conf import settings

from retail.clients.base import RequestClient, InternalAuthentication
from retail.interfaces.clients.flows.interface import FlowsClientInterface
from retail.interfaces.jwt import JWTInterface
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase


class FlowsClient(RequestClient, FlowsClientInterface):
    def __init__(self, jwt_usecase: Optional[JWTInterface] = None):
        self.base_url = settings.FLOWS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()
        self.jwt_usecase = jwt_usecase or JWTUsecase()

    def _module_jwt_headers(self, project_uuid: str) -> Dict[str, str]:
        """Bearer JWT with ``project_uuid`` for public Flows v2 routes.

        Public v2 routes (``groups.json``, ``contacts.json``,
        ``contact_actions.json``) do not accept the internal OIDC token
        used by ``/api/v2/internals/*``.
        """
        token = self.jwt_usecase.generate_jwt_token(project_uuid)
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

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

    def get_contact_groups(self, project_uuid: str, name: str) -> dict:
        """GET /api/v2/groups.json filtered by name for the given project."""
        url = f"{self.base_url}/api/v2/groups.json"
        response = self.make_request(
            url,
            method="GET",
            params={"project": str(project_uuid), "name": name},
            headers=self._module_jwt_headers(project_uuid),
        )
        return response.json()

    def create_contact_group(self, project_uuid: str, name: str) -> dict:
        """POST /api/v2/groups.json to create a group in the given project."""
        url = f"{self.base_url}/api/v2/groups.json"
        response = self.make_request(
            url,
            method="POST",
            params={"project": str(project_uuid)},
            json={"name": name},
            headers=self._module_jwt_headers(project_uuid),
        )
        return response.json()

    def create_contact(
        self, project_uuid: str, name: str, urns: List[str], groups: List[str]
    ) -> dict:
        """POST /api/v2/contacts.json already assigned to ``groups``."""
        url = f"{self.base_url}/api/v2/contacts.json"
        response = self.make_request(
            url,
            method="POST",
            params={"project": str(project_uuid)},
            json={"name": name, "urns": urns, "groups": groups},
            headers=self._module_jwt_headers(project_uuid),
        )
        return response.json()

    def add_contact_to_group(
        self, project_uuid: str, contacts: List[str], group: str
    ) -> dict:
        """POST /api/v2/contact_actions.json with ``action=add``."""
        url = f"{self.base_url}/api/v2/contact_actions.json"
        response = self.make_request(
            url,
            method="POST",
            params={"project": str(project_uuid)},
            json={"contacts": contacts, "action": "add", "group": group},
            headers=self._module_jwt_headers(project_uuid),
        )
        return response.json()
