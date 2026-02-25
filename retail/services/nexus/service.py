import logging

from typing import Dict, Optional, Tuple

from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.clients.exceptions import CustomAPIException

logger = logging.getLogger(__name__)


class NexusService:
    def __init__(self, nexus_client: NexusClientInterface = None):
        self.nexus_client = nexus_client

    def list_agents(self, project_uuid: str) -> Optional[Dict]:
        """
        Lists all available agents for a project.
        """
        try:
            return self.nexus_client.list_agents(project_uuid)
        except CustomAPIException as e:
            logger.error(
                f"Code: {e.status_code} when listing agents for project {project_uuid}. Error: {e}"
            )
            return None

    def integrate_agent(self, project_uuid: str, agent_uuid: str) -> Optional[Dict]:
        """
        Integrates an agent into a project.
        """
        try:
            return self.nexus_client.integrate_agent(project_uuid, agent_uuid)
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} when integrating agent {agent_uuid} "
                f"for project {project_uuid}."
            )
            return None

    def remove_agent(self, project_uuid: str, agent_uuid: str) -> Optional[Dict]:
        """
        Removes an agent from a project.
        """
        try:
            return self.nexus_client.remove_agent(project_uuid, agent_uuid)
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} when removing agent {agent_uuid} "
                f"from project {project_uuid}."
            )
            return None

    def list_integrated_agents(self, project_uuid: str) -> Optional[Dict]:
        """
        Lists all agents currently integrated with a project.
        """
        try:
            return self.nexus_client.list_integrated_agents(project_uuid)
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} when listing integrated agents "
                f"for project {project_uuid}."
            )
            return None

    def check_agent_builder_exists(self, project_uuid: str) -> Optional[Dict]:
        """
        Checks whether the agent manager has been configured for a project.
        """
        try:
            return self.nexus_client.check_agent_builder_exists(project_uuid)
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} checking agent builder existence "
                f"for project {project_uuid}: {e}"
            )
            return None

    def configure_agent_attributes(
        self, project_uuid: str, agent_payload: Dict
    ) -> Optional[Dict]:
        """
        Sets the manager attributes for a project.
        """
        try:
            return self.nexus_client.configure_agent_attributes(
                project_uuid, agent_payload
            )
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} configuring agent attributes "
                f"for project {project_uuid}: {e}"
            )
            return None

    def upload_content_base_file(
        self,
        project_uuid: str,
        file: Tuple[str, bytes, str],
        extension_file: str = "txt",
    ) -> Optional[Dict]:
        """
        Uploads a file to the project's inline content base in Nexus.

        Args:
            project_uuid: The project's unique identifier.
            file: Tuple of (filename, file_bytes, content_type).
            extension_file: The file extension without dot (e.g. "txt").

        Returns:
            Dict with upload response or None on failure.
        """
        try:
            return self.nexus_client.upload_content_base_file(
                project_uuid, file, extension_file
            )
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} when uploading content base file "
                f"for project {project_uuid}: {e}"
            )
            return None
