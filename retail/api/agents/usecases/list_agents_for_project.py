import logging
from dataclasses import dataclass
from typing import Optional

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_management.serializers import GalleryAgentSerializer
from retail.agents.domains.agent_management.usecases.list import ListAgentsUseCase
from retail.projects.models import Project
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


@dataclass
class ListAgentsResult:
    """Result data class for list agents usecase."""

    store_type: str
    nexus_agents: Optional[list[dict]] = None
    gallery_agents: Optional[list[dict]] = None

    def to_dict(self) -> dict:
        """Convert result to dictionary for API response."""
        data = {"store_type": self.store_type}

        if self.nexus_agents is not None:
            data["nexus_agents"] = self.nexus_agents

        if self.gallery_agents is not None:
            data["gallery_agents"] = self.gallery_agents

        return data


class ListAgentsForProjectUseCase:
    """
    Use case to list all available agents for a project.

    Aggregates agents from multiple sources:
    - Nexus service agents
    - Gallery agents (CLI-pushed agents)
    """

    def __init__(self, nexus_service: NexusService):
        self._nexus_service = nexus_service

    def execute(self, project_uuid: str) -> ListAgentsResult:
        """
        Execute the use case to list agents for a project.

        Args:
            project_uuid: The project UUID to list agents for.

        Returns:
            ListAgentsResult with agents from all sources.

        Raises:
            NotFound: If project does not exist.
        """
        project = self._get_project(project_uuid)
        store_type = self._get_store_type(project)

        nexus_agents = self._fetch_nexus_agents(project_uuid)
        gallery_agents = self._fetch_gallery_agents(project_uuid)

        return ListAgentsResult(
            store_type=store_type,
            nexus_agents=nexus_agents,
            gallery_agents=gallery_agents,
        )

    def _get_project(self, project_uuid: str) -> Project:
        """Fetch project by UUID."""
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise NotFound(detail="Project not found")

    def _get_store_type(self, project: Project) -> str:
        """Extract store type from project VTEX config."""
        vtex_config = project.config.get("vtex_config", {})
        return vtex_config.get("vtex_store_type", "")

    def _fetch_nexus_agents(self, project_uuid: str) -> Optional[list[dict]]:
        """Fetch agents from Nexus service."""
        try:
            agents = self._nexus_service.list_agents(project_uuid)
            return agents if agents else None
        except Exception as e:
            logger.error(f"Error fetching nexus agents: {e}")
            return None

    def _fetch_gallery_agents(self, project_uuid: str) -> Optional[list[dict]]:
        """Fetch gallery agents (CLI-pushed agents)."""
        try:
            agents = ListAgentsUseCase.execute(project_uuid)
            serializer = GalleryAgentSerializer(
                agents, many=True, context={"project_uuid": project_uuid}
            )
            return serializer.data
        except Exception as e:
            logger.error(f"Error fetching gallery agents: {e}")
            return None
