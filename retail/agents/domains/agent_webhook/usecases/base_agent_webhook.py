import logging

from typing import Optional

from django.core.cache import cache

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project


logger = logging.getLogger(__name__)


class BaseAgentWebhookUseCase:
    """
    Base class for agent webhook use cases that provides common functionality
    for retrieving integrated agents and projects.
    """

    def get_integrated_agent_if_exists(
        self, project: Project, agent_uuid: str
    ) -> Optional[IntegratedAgent]:
        """
        Retrieve the integrated agent if it exists, with caching for 6 hours.

        Args:
            project (Project): The project instance.
            agent_uuid (str): The UUID of the agent to retrieve.

        Returns:
            Optional[IntegratedAgent]: The integrated agent if found, otherwise None.
        """
        if not agent_uuid:
            logger.warning("Agent UUID is not provided.")
            return None

        cache_key = f"integrated_agent_{agent_uuid}_{str(project.uuid)}"
        integrated_agent = cache.get(cache_key)

        if integrated_agent:
            return integrated_agent

        try:
            integrated_agent = IntegratedAgent.objects.get(
                agent__uuid=agent_uuid,
                project=project,
                is_active=True,
            )
            cache.set(cache_key, integrated_agent, timeout=21600)  # 6 hours
        except IntegratedAgent.DoesNotExist:
            logger.info(
                f"No active integrated agent found for agent UUID: {agent_uuid}"
            )
            return None

        return integrated_agent

    def get_project_by_vtex_account(self, vtex_account: str) -> Optional[Project]:
        """
        Get the project by VTEX account, with caching.

        Args:
            vtex_account (str): The VTEX account identifier.

        Returns:
            Optional[Project]: The project associated with the VTEX account.
        """
        cache_key = f"project_by_vtex_account_{vtex_account}"
        project = cache.get(cache_key)

        if project:
            return project

        try:
            project = Project.objects.get(vtex_account=vtex_account)
            cache.set(cache_key, project, timeout=43200)  # 12 hours
            return project
        except Project.DoesNotExist:
            logger.info(f"Project not found for VTEX account {vtex_account}.")
            return None
        except Project.MultipleObjectsReturned:
            logger.error(
                f"Multiple projects found for VTEX account {vtex_account}.",
                exc_info=True,
            )
            return None
