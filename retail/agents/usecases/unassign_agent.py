import logging
from typing import Callable

from django.conf import settings
from django.core.cache import cache

from rest_framework.exceptions import NotFound

from retail.agents.models import IntegratedAgent, Agent
from weni_datalake_sdk.clients.client import send_data

logger = logging.getLogger(__name__)


class UnassignAgentUseCase:
    def __init__(self, audit_func: Callable = None):
        self.audit_func = send_data if audit_func is None else audit_func

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
        self._register_agent_unassign_event(agent, project_uuid, integrated_agent)
        self._clear_cache(agent, integrated_agent)

    def _register_agent_unassign_event(self, agent, project_uuid, integrated_agent):
        data = {
            "event": "agent_unassigned",
            "agent_uuid": str(agent.uuid),
            "project_uuid": str(project_uuid),
            "integrated_agent_uuid": str(integrated_agent.uuid),
            "is_active": integrated_agent.is_active,
        }

        self.audit_func("YourPath", data)
        logger.info(f"Agent unassignment event registered for agent {agent.uuid}")

    def _clear_cache(self, agent: Agent, integrated_agent: IntegratedAgent) -> None:
        if not settings.ORDER_STATUS_AGENT_UUID:
            logger.warning("ORDER_STATUS_AGENT_UUID is not set in settings.")
            return

        if str(agent.uuid) == settings.ORDER_STATUS_AGENT_UUID:
            cache_key = f"integrated_agent_{settings.ORDER_STATUS_AGENT_UUID}_{str(integrated_agent.project.uuid)}"
            cache.delete(cache_key)
            logger.info(f"Cleared cache for key: {cache_key}")
