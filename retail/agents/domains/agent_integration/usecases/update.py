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


class AbandonedCartConfigData(TypedDict, total=False):
    header_image_type: str
    abandonment_time_minutes: int
    minimum_cart_value: Optional[float]
    notification_cooldown_hours: Optional[int]


class UpdateIntegratedAgentData(TypedDict, total=False):
    contact_percentage: Optional[int]
    global_rule: Optional[str]
    abandoned_cart_config: Optional[AbandonedCartConfigData]


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

        if "abandoned_cart_config" in data:
            abandoned_cart_config = data.get("abandoned_cart_config")
            self._update_abandoned_cart_config(integrated_agent, abandoned_cart_config)

        integrated_agent.save()

        # Clear the webhook cache (30 seconds)
        self.cache_handler.clear_cached_agent(integrated_agent.uuid)

        # Clear the order status cache (6 hours) if this is an order status agent
        self._clear_order_status_cache(integrated_agent)

        return integrated_agent

    def _update_abandoned_cart_config(
        self,
        integrated_agent: IntegratedAgent,
        config_data: Optional[AbandonedCartConfigData],
    ) -> None:
        """
        Update abandoned cart configuration in the integrated agent's config.

        Only updates the fields that are provided in config_data.
        """
        if config_data is None:
            return

        # Initialize config if not present
        if integrated_agent.config is None:
            integrated_agent.config = {}

        # Get existing abandoned_cart config or create empty one
        abandoned_cart = integrated_agent.config.get("abandoned_cart", {})

        # Update only the fields that are provided
        if "header_image_type" in config_data:
            abandoned_cart["header_image_type"] = config_data["header_image_type"]

        if "abandonment_time_minutes" in config_data:
            abandoned_cart["abandonment_time_minutes"] = config_data[
                "abandonment_time_minutes"
            ]

        if "minimum_cart_value" in config_data:
            abandoned_cart["minimum_cart_value"] = config_data["minimum_cart_value"]

        if "notification_cooldown_hours" in config_data:
            abandoned_cart["notification_cooldown_hours"] = config_data[
                "notification_cooldown_hours"
            ]

        integrated_agent.config["abandoned_cart"] = abandoned_cart

        logger.info(
            f"Updated abandoned cart config for agent {integrated_agent.uuid}: "
            f"{abandoned_cart}"
        )

    def _clear_order_status_cache(self, integrated_agent: IntegratedAgent) -> None:
        """
        Clear the order status cache if this is an order status agent.

        This cache is used in AgentOrderStatusUpdateUsecase and has a 6-hour timeout.
        """
        if not settings.ORDER_STATUS_AGENT_UUID:
            return

        # Check if this is an order status agent (official or custom with parent_agent_uuid)
        is_order_status_agent = (
            str(integrated_agent.agent.uuid) == settings.ORDER_STATUS_AGENT_UUID
            or integrated_agent.parent_agent_uuid is not None
        )

        if is_order_status_agent:
            cache_key = f"order_status_agent_{str(integrated_agent.project.uuid)}"
            cache.delete(cache_key)
            logger.info(
                f"Cleared order status cache for agent {integrated_agent.uuid} with key: {cache_key}"
            )
