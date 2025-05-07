from typing import Dict, Optional

from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.clients.exceptions import CustomAPIException


class NexusService:
    def __init__(self, nexus_client: NexusClientInterface):
        self.nexus_client = nexus_client

    def list_agents(self, project_uuid: str) -> Optional[Dict]:
        """
        Lists all available agents for a project.
        """
        try:
            return self.nexus_client.list_agents(project_uuid)
        except CustomAPIException as e:
            print(
                f"Code: {e.status_code} when listing agents for project {project_uuid}. Error: {str(e)}"
            )
            return None

    def integrate_agent(self, project_uuid: str, agent_uuid: str) -> Optional[Dict]:
        """
        Integrates an agent into a project.
        """
        try:
            return self.nexus_client.integrate_agent(project_uuid, agent_uuid)
        except CustomAPIException as e:
            print(
                f"Error {e.status_code} when integrating agent {agent_uuid} for project {project_uuid}."
            )
            return None

    def remove_agent(self, project_uuid: str, agent_uuid: str) -> Optional[Dict]:
        """
        Removes an agent from a project.
        """
        try:
            return self.nexus_client.remove_agent(project_uuid, agent_uuid)
        except CustomAPIException as e:
            print(
                f"Error {e.status_code} when removing agent {agent_uuid} from project {project_uuid}."
            )
            return None

    def list_integrated_agents(self, project_uuid: str) -> Optional[Dict]:
        """
        Lists all agents currently integrated with a project.
        """
        try:
            return self.nexus_client.list_integrated_agents(project_uuid)
        except CustomAPIException as e:
            print(
                f"Error {e.status_code} when listing integrated agents for project {project_uuid}."
            )
            return None
