"""Client for connection with Nexus"""

from django.conf import settings
from typing import Dict

from retail.clients.base import RequestClient, InternalAuthentication
from retail.interfaces.clients.nexus.client import NexusClientInterface


class NexusClient(RequestClient, NexusClientInterface):
    def __init__(self):
        self.base_url = settings.NEXUS_REST_ENDPOINT
        self.authentication_instance = InternalAuthentication()

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
        payload = {"assign": True}

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
        payload = {"assign": False}

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
