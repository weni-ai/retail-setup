from typing import Dict, Protocol, Tuple


class NexusClientInterface(Protocol):
    """
    Interface for Nexus client operations.
    """

    def list_agents(self, project_uuid: str) -> Dict:
        """
        Lists all available agents for a project.

        Args:
            project_uuid (str): The project's unique identifier.

        Returns:
            Dict: Available agents data.
        """
        ...

    def integrate_agent(self, project_uuid: str, agent_uuid: str) -> Dict:
        """
        Integrates an agent to a project.

        Args:
            project_uuid (str): The project's unique identifier.
            agent_uuid (str): The agent's unique identifier.

        Returns:
            Dict: Integration response data.
        """
        ...

    def remove_agent(self, project_uuid: str, agent_uuid: str) -> Dict:
        """
        Removes an agent from a project.

        Args:
            project_uuid (str): The project's unique identifier.
            agent_uuid (str): The agent's unique identifier.

        Returns:
            Dict: Removal response data.
        """
        ...

    def list_integrated_agents(self, project_uuid: str) -> Dict:
        """
        Lists all agents integrated to a project.

        Args:
            project_uuid (str): The project's unique identifier.

        Returns:
            Dict: Integrated agents data.
        """
        ...

    def check_agent_builder_exists(self, project_uuid: str) -> Dict:
        """
        Checks whether the agent manager has been configured for a project.

        Args:
            project_uuid: The project's unique identifier.

        Returns:
            Dict with "data" containing agent info and "has_agent" flag.
        """
        ...

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
        ...

    def upload_content_base_file(
        self,
        project_uuid: str,
        file: Tuple[str, bytes, str],
        extension_file: str = "txt",
    ) -> Dict:
        """
        Uploads a file to the project's inline content base in Nexus.

        Args:
            project_uuid: The project's unique identifier.
            file: Tuple of (filename, file_bytes, content_type).
            extension_file: The file extension without dot (e.g. "txt").

        Returns:
            Dict: Upload response data.
        """
        ...
