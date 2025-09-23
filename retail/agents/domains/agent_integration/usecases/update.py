import logging
from typing import TypedDict, Optional

from rest_framework.exceptions import NotFound, ValidationError

from uuid import UUID

from django.core.cache import cache
from django.conf import settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_integration.services.global_rule import GlobalRule
from retail.agents.shared.cache import (
    IntegratedAgentCacheHandler,
    IntegratedAgentCacheHandlerRedis,
)

logger = logging.getLogger(__name__)


class UpdateIntegratedAgentData(TypedDict):
    contact_percentage: Optional[int]
    global_rule: Optional[str]


class UpdateIntegratedAgentUseCase:
    def __init__(
        self,
        global_rule: Optional[GlobalRule] = None,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
    ):
        self.global_rule = global_rule or GlobalRule()
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found {integrated_agent_uuid}")

    def _is_valid_percentage(self, percentage: int) -> bool:
        return 0 <= percentage <= 100

    def execute(
        self, integrated_agent: IntegratedAgent, data: UpdateIntegratedAgentData
    ) -> IntegratedAgent:
        if "contact_percentage" in data:
            contact_percentage = data.get("contact_percentage")

            if not self._is_valid_percentage(contact_percentage):
                raise ValidationError({"contact_percentage": "Invalid percentage"})

            integrated_agent.contact_percentage = contact_percentage

        if "global_rule" in data:
            global_rule = data.get("global_rule")

            if global_rule is None or global_rule == "":
                global_rule_code = None
                global_rule_prompt = None
            else:
                global_rule_code = (
                    self.global_rule.generate(integrated_agent, global_rule)
                    .validate()
                    .get_global_rule()
                )
                global_rule_prompt = global_rule

            integrated_agent.global_rule_code = global_rule_code
            integrated_agent.global_rule_prompt = global_rule_prompt

        integrated_agent.save()

        # Clear the webhook cache (30 seconds)
        self.cache_handler.clear_cached_agent(integrated_agent.uuid)

        # Clear the order status cache (6 hours) if this is an order status agent
        self._clear_order_status_cache(integrated_agent)

        return integrated_agent

    def _clear_order_status_cache(self, integrated_agent: IntegratedAgent) -> None:
        """
        Clear the order status cache if this is an order status agent.

        This cache is used in AgentOrderStatusUpdateUsecase and has a 6-hour timeout.
        """
        if not settings.ORDER_STATUS_AGENT_UUID:
            return

        # Check if this is an order status agent (official or custom with parent_agent_uuid)
        is_order_status_agent = str(
            integrated_agent.agent.uuid
        ) == settings.ORDER_STATUS_AGENT_UUID or (
            integrated_agent.parent_agent_uuid
            and str(integrated_agent.parent_agent_uuid)
            == settings.ORDER_STATUS_AGENT_UUID
        )

        if is_order_status_agent:
            cache_key = f"integrated_agent_{settings.ORDER_STATUS_AGENT_UUID}_{str(integrated_agent.project.uuid)}"
            cache.delete(cache_key)
            logger.info(
                f"Cleared order status cache for agent {integrated_agent.uuid} with key: {cache_key}"
            )
