import logging
from typing import TypedDict, Optional

from rest_framework.exceptions import NotFound, ValidationError

from uuid import UUID

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


class PaymentRecoveryConfigData(TypedDict, total=False):
    minimum_order_value: Optional[float]


class UpdateIntegratedAgentData(TypedDict, total=False):
    contact_percentage: Optional[int]
    global_rule: Optional[str]
    abandoned_cart_config: Optional[AbandonedCartConfigData]
    payment_recovery_config: Optional[PaymentRecoveryConfigData]


class UpdateIntegratedAgentUseCase:
    """Apply partial updates to an integrated agent and invalidate its cache."""

    def __init__(
        self,
        global_rule: Optional[GlobalRule] = None,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
    ):
        """Initialize the use case with its collaborators.

        Args:
            global_rule: Service that generates and validates the global rule
                code. Defaults to a concrete ``GlobalRule`` instance.
            cache_handler: Handler used to invalidate cached agent data.
                Defaults to a concrete ``IntegratedAgentCacheHandlerRedis``.
        """
        self.global_rule = global_rule or GlobalRule()
        self.cache_handler = cache_handler or IntegratedAgentCacheHandlerRedis()

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        """Retrieve an active integrated agent by UUID.

        Args:
            integrated_agent_uuid: UUID of the integrated agent.

        Returns:
            IntegratedAgent: The matching active integrated agent instance.

        Raises:
            NotFound: If no active integrated agent exists with the given UUID.
        """
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
        """Apply the provided partial update and invalidate the agent cache.

        Only the keys present in ``data`` are updated; omitted keys are left
        untouched.

        Args:
            integrated_agent: The integrated agent to update.
            data: Partial update payload validated by the serializer.

        Returns:
            IntegratedAgent: The updated integrated agent instance.

        Raises:
            ValidationError: If ``contact_percentage`` is outside 0-100.
        """
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

        if "payment_recovery_config" in data:
            payment_recovery_config = data.get("payment_recovery_config")
            self._update_payment_recovery_config(
                integrated_agent, payment_recovery_config
            )

        integrated_agent.save()

        self.cache_handler.invalidate_all_for(integrated_agent)

        return integrated_agent

    def _update_abandoned_cart_config(
        self,
        integrated_agent: IntegratedAgent,
        config_data: Optional[AbandonedCartConfigData],
    ) -> None:
        """Update abandoned cart configuration in the integrated agent's config.

        Only updates the fields provided in ``config_data``.

        Args:
            integrated_agent: The integrated agent whose config will be updated.
            config_data: Partial abandoned cart config; ``None`` is a no-op.
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

    def _update_payment_recovery_config(
        self,
        integrated_agent: IntegratedAgent,
        config_data: Optional[PaymentRecoveryConfigData],
    ) -> None:
        """Update payment recovery (PIX) configuration in the integrated agent's config.

        Only updates the fields provided in ``config_data``, preserving
        infrastructure keys (e.g. ``hook_created``, ``delay_minutes``) set
        during agent assignment.

        Args:
            integrated_agent: The integrated agent whose config will be updated.
            config_data: Partial payment recovery config; ``None`` is a no-op.
        """
        if config_data is None:
            return

        if integrated_agent.config is None:
            integrated_agent.config = {}

        payment_recovery = integrated_agent.config.get("payment_recovery", {})

        if "minimum_order_value" in config_data:
            payment_recovery["minimum_order_value"] = config_data["minimum_order_value"]

        integrated_agent.config["payment_recovery"] = payment_recovery

        logger.info(
            f"Updated payment recovery config for agent {integrated_agent.uuid}: "
            f"{payment_recovery}"
        )
