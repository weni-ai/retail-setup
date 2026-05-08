import logging

from typing import Optional

from django.conf import settings
from django.core.cache import cache

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.cache import (
    AgentRole,
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
    ROLE_SETTING_NAMES,
)
from retail.projects.models import Project


logger = logging.getLogger(__name__)


class BaseAgentWebhookUseCase:
    """
    Base class for agent webhook use cases that provides common functionality
    for retrieving integrated agents and projects.
    """

    def __init__(
        self,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
    ) -> None:
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()

    def get_integrated_agent_if_exists(
        self, project: Project, role: AgentRole
    ) -> Optional[IntegratedAgent]:
        """
        Retrieve the integrated agent that fulfills ``role`` for ``project``.

        Hits the role cache first (6h TTL) and falls back to a DB
        lookup keyed by the ``Agent.uuid`` configured in settings for
        ``role``. The lookup is then cached for subsequent calls.

        Returns ``None`` when the role setting is not configured or
        when no active integrated agent exists for the project.
        """
        agent_uuid = self._resolve_role_agent_uuid(role)
        if not agent_uuid:
            return None

        cached = self.cache_handler.get_role_agent(project.uuid, role)
        if cached is not None:
            return cached

        try:
            integrated_agent = IntegratedAgent.objects.get(
                agent__uuid=agent_uuid,
                project=project,
                is_active=True,
            )
        except IntegratedAgent.DoesNotExist:
            logger.info(
                f"No active integrated agent found for role {role.value} "
                f"(agent_uuid={agent_uuid}, project={project.uuid})"
            )
            return None

        self.cache_handler.set_role_agent(integrated_agent, role)
        return integrated_agent

    @staticmethod
    def _resolve_role_agent_uuid(role: AgentRole) -> Optional[str]:
        """Look up the ``Agent.uuid`` configured in settings for ``role``.

        Each role maps to one Django setting via ``ROLE_SETTING_NAMES``
        and that setting holds the canonical ``Agent.uuid``. Returns
        ``None`` (and logs) when the setting is empty so the caller can
        short-circuit without a DB hit.

        Example:
            role=AgentRole.ABANDONED_CART
                → setting_name = "ABANDONED_CART_AGENT_UUID"
                → returns settings.ABANDONED_CART_AGENT_UUID, e.g.
                  "0a1b2c3d-...-abc"; or ``None`` when the setting is
                  empty in this environment.
        """
        setting_name = ROLE_SETTING_NAMES[role]
        agent_uuid = getattr(settings, setting_name, "")
        if not agent_uuid:
            logger.warning(f"{setting_name} is not configured in settings.")
            return None
        return agent_uuid

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
