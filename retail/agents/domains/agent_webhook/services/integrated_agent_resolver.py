import logging
from typing import Optional
from uuid import UUID

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.cache import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)
from retail.agents.shared.webhook_urls import ROLES_WITH_DEDICATED_WEBHOOK


logger = logging.getLogger(__name__)

IGNORE_INTEGRATED_AGENT_UUID = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"


class IntegratedAgentWebhookResolver:
    """Resolve active integrated agents for inbound agent webhook dispatch."""

    def __init__(
        self,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
    ) -> None:
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()

    def resolve(self, uuid: UUID) -> Optional[IntegratedAgent]:
        """Return an active integrated agent when it exists and is not blocked."""
        if str(uuid) == IGNORE_INTEGRATED_AGENT_UUID:
            logger.info(f"Integrated agent is blocked: {uuid}")
            return None

        cached_integrated_agent = self.cache_handler.get_cached_agent(uuid)

        if cached_integrated_agent is not None:
            if self._is_project_blocked(cached_integrated_agent):
                logger.info(f"Project is blocked, skipping cached agent: {uuid}")
                return None
            return cached_integrated_agent

        try:
            db_integrated_agent = IntegratedAgent.objects.select_related(
                "project", "agent"
            ).get(uuid=uuid, is_active=True)
        except IntegratedAgent.DoesNotExist:
            logger.info(f"Integrated agent not found: {uuid}")
            return None

        if self._is_project_blocked(db_integrated_agent):
            logger.info(f"Project is blocked, skipping agent: {uuid}")
            return None

        self.cache_handler.set_cached_agent(db_integrated_agent)
        return db_integrated_agent

    def should_skip_generic_webhook_dispatch(self, uuid: UUID) -> bool:
        """Return True when the generic webhook must not enqueue a task.

        Missing or blocked agents return False so the Celery task can still
        run and record the skip.
        """
        integrated_agent = self.resolve(uuid)
        if integrated_agent is None:
            return False

        role = IntegratedAgentCacheHandler.resolve_role(integrated_agent)
        if role not in ROLES_WITH_DEDICATED_WEBHOOK:
            return False

        logger.warning(
            f"Agent role {role.value} must use dedicated webhook - "
            f"integrated_agent={uuid}"
        )
        return True

    @staticmethod
    def _is_project_blocked(integrated_agent: IntegratedAgent) -> bool:
        return integrated_agent.project.is_blocked
