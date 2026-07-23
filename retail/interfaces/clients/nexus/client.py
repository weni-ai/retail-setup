from typing import Dict, List, Protocol, Tuple


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

    def create_agent_credentials(
        self,
        project_uuid: str,
        agent_uuid: str,
        credentials: List[Dict],
    ) -> Dict:
        """
        Creates one or more credentials on a Nexus agent for a project.

        Args:
            project_uuid: The project's unique identifier.
            agent_uuid: The agent that will receive the credentials.
            credentials: List of credential dicts. Each dict accepts
                ``name``, ``label``, ``placeholder``, ``is_confidential``
                and ``value`` keys.

        Returns:
            Dict with the Nexus response (typically including the list
            of created credential names).
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

    def list_team_agents(self, project_uuid: str) -> Dict:
        """
        Lists agents integrated to a project, including shared/official agents
        assigned from other projects (active and inactive).

        Args:
            project_uuid: The project's unique identifier.

        Returns:
            Dict with ``manager`` and ``agents`` keys.
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
            agent_payload: Dict with "agent", optional "links", and optional
                "instructions" keys.

        Returns:
            Dict with the Nexus response.
        """
        ...

    def upload_content_base_files_batch(
        self,
        project_uuid: str,
        files: List[Tuple[str, bytes, str]],
        extension_file: str = "txt",
    ) -> Dict:
        """
        Uploads up to 25 files to the project's inline content base in Nexus.

        Args:
            project_uuid: The project's unique identifier.
            files: List of (filename, file_bytes, content_type) tuples.
            extension_file: The file extension without dot (e.g. "txt").

        Returns:
            Dict with uploaded file metadata and optional errors.
        """
        ...

    def get_content_base_batch_progress(
        self,
        project_uuid: str,
        file_uuids: List[str],
    ) -> Dict:
        """
        Returns aggregate ingestion progress for a batch of uploaded files.

        Args:
            project_uuid: The project's unique identifier.
            file_uuids: UUIDs returned by the batch upload endpoint.

        Returns:
            Dict with aggregate progress fields (total, completed, status, etc.).
        """
        ...
