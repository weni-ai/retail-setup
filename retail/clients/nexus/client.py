"""Client for connection with Nexus"""

from django.conf import settings
from typing import Dict, Tuple

from retail.clients.base import RequestClient, InternalAuthentication
from retail.interfaces.clients.nexus.client import NexusClientInterface


class NexusClient(RequestClient, NexusClientInterface):
    def __init__(self):
        self.base_url = settings.NEXUS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

    def _get_auth_header(self) -> dict:
        """Returns authorization header without Content-Type (for file uploads)."""
        return {"Authorization": self.authentication_instance.headers["Authorization"]}

    def list_agents(self, project_uuid: str) -> Dict:
        """
        Lists all available agents for a project.

        Args:
            project_uuid (str): The project's unique identifier.

        Returns:
            Dict: Available agents data.
        """
        url = f"{self.base_url}/api/agents/app-official/{str(project_uuid)}"

        response = self.make_request(
            url, method="GET", headers=self.authentication_instance.headers
        )
        return response.json()

    def integrate_agent(self, project_uuid: str, agent_uuid: str) -> Dict:
        """
        Integrates an agent to a project.

        Args:
            project_uuid (str): The project's unique identifier.
            agent_uuid (str): The agent's unique identifier.

        Returns:
            Dict: Integration response data.
        """
        url = f"{self.base_url}/api/project/{str(project_uuid)}/app-assign/{str(agent_uuid)}"
        payload = {"assigned": True}

        response = self.make_request(
            url,
            method="PATCH",
            json=payload,
            headers=self.authentication_instance.headers,
        )
        return response.json()

    def remove_agent(self, project_uuid: str, agent_uuid: str) -> Dict:
        """
        Removes an agent from a project.

        Args:
            project_uuid (str): The project's unique identifier.
            agent_uuid (str): The agent's unique identifier.

        Returns:
            Dict: Removal response data.
        """
        url = f"{self.base_url}/api/project/{str(project_uuid)}/app-assign/{str(agent_uuid)}"
        payload = {"assigned": False}

        response = self.make_request(
            url,
            method="PATCH",
            json=payload,
            headers=self.authentication_instance.headers,
        )
        return response.json()

    def list_integrated_agents(self, project_uuid: str) -> Dict:
        """
        Lists all agents integrated to a project.

        Args:
            project_uuid (str): The project's unique identifier.

        Returns:
            Dict: Integrated agents data.
        """
        url = f"{self.base_url}/api/agents/app-my-agents/{str(project_uuid)}"

        response = self.make_request(
            url, method="GET", headers=self.authentication_instance.headers
        )
        return response.json()

    def check_agent_builder_exists(self, project_uuid: str) -> Dict:
        """
        Checks whether the agent manager has been configured for a project.

        Args:
            project_uuid: The project's unique identifier.

        Returns:
            Dict with "data" containing agent info and "has_agent" flag.
        """
        url = f"{self.base_url}/api/commerce/check-exists-agent-builder"
        response = self.make_request(
            url,
            method="GET",
            headers=self.authentication_instance.headers,
            params={"project_uuid": project_uuid},
        )
        return response.json()

    def configure_agent_attributes(
        self,
        project_uuid: str,
        agent_payload: Dict,
    ) -> Dict:
        """
        Sets the manager attributes (name, goal, role, personality) for a project.

        Args:
            project_uuid: The project's unique identifier.
            agent_payload: Dict with "agent" and optional "links" keys.

        Returns:
            Dict with the Nexus response.
        """
        url = f"{self.base_url}/api/{project_uuid}/commerce-router/"
        response = self.make_request(
            url,
            method="POST",
            json=agent_payload,
            headers=self.authentication_instance.headers,
        )
        return response.json()

    def upload_content_base_file(
        self,
        project_uuid: str,
        file: Tuple[str, bytes, str],
        extension_file: str = "txt",
    ) -> Dict:
        """
        Uploads a file to the project's inline content base in Nexus.

        Sends the actual binary file as multipart/form-data along with
        the required metadata fields (extension_file, load_type).

        Args:
            project_uuid: The project's unique identifier.
            file: Tuple of (filename, file_bytes, content_type).
            extension_file: The file extension without dot (e.g. "txt").

        Returns:
            Dict: Upload response data.
        """
        url = f"{self.base_url}/api/{str(project_uuid)}/inline-content-base-file/"

        response = self.make_request(
            url,
            method="POST",
            headers=self._get_auth_header(),
            files={"file": file},
            data={
                "extension_file": extension_file,
                "load_type": "pdfminer",
            },
        )
        return response.json()
