import logging

from django.conf import settings
from django.core.cache import cache

from rest_framework.exceptions import NotFound

from retail.agents.models import IntegratedAgent, Agent


logger = logging.getLogger(__name__)


class UnassignAgentUseCase:
    def _get_integrated_agent(self, agent: Agent, project_uuid: str) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(
                agent=agent, project__uuid=project_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound("Integrated agent not found")

    def execute(self, agent: Agent, project_uuid: str) -> None:
        integrated_agent = self._get_integrated_agent(agent, project_uuid)
        integrated_agent.is_active = False
        integrated_agent.save()
        self._clear_cache(agent, integrated_agent)

    def _clear_cache(self, agent: Agent, integrated_agent: IntegratedAgent) -> None:
        if not settings.ORDER_STATUS_AGENT_UUID:
            logger.warning("ORDER_STATUS_AGENT_UUID is not set in settings.")
            return

        if str(agent.uuid) == settings.ORDER_STATUS_AGENT_UUID:
            cache_key = f"integrated_agent_{settings.ORDER_STATUS_AGENT_UUID}_{str(integrated_agent.project.uuid)}"
            cache.delete(cache_key)
            logger.info(f"Cleared cache for key: {cache_key}")
