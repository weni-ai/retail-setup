import logging

from typing import Callable

from datetime import datetime

from rest_framework.exceptions import NotFound

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.shared.cache import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)

from weni_datalake_sdk.clients.client import send_commerce_webhook_data
from weni_datalake_sdk.paths.commerce_webhook import CommerceWebhookPath

logger = logging.getLogger(__name__)


class UnassignAgentUseCase:
    def __init__(
        self,
        audit_func: Callable = None,
        cache_handler: IntegratedAgentCacheHandler | None = None,
    ):
        self.audit_func = audit_func or send_commerce_webhook_data
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()

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
        self._register_agent_unassign_event(agent, project_uuid)
        self._clear_cache(integrated_agent)

    def _register_agent_unassign_event(self, agent: Agent, project_uuid: str):
        """
        Register agent unassignment event with structured data according to protobuf schema.

        This event is triggered when an agent is unassigned from a project.
        Only relevant fields for this event type are included.

        Args:
            agent: The agent being unassigned
            project_uuid: The project UUID
        """

        # Build structured data according to protobuf schema
        # Only include fields that are available for this event type
        event_data = {
            "data": {"event_type": "agent_unassigned"},
            "date": datetime.now().isoformat(),
            "project": project_uuid,
            "agent": str(agent.uuid),
        }

        self.audit_func(CommerceWebhookPath, event_data)
        logger.info(f"Agent unassignment event registered for agent {agent.uuid}")

    def _clear_cache(self, integrated_agent: IntegratedAgent) -> None:
        """Drop every cache entry derived from this IntegratedAgent.

        Defensive against cache backend failures: a Redis hiccup must
        not break the unassign flow, so we log and continue.
        """
        try:
            self.cache_handler.invalidate_all_for(integrated_agent)
            logger.info(
                f"Invalidated all caches for integrated agent {integrated_agent.uuid}"
            )
        except Exception as exc:
            logger.warning(
                f"Failed to invalidate caches for integrated agent "
                f"{integrated_agent.uuid}: {exc}"
            )
