"""
Hard-coded onboarding agents.

Each class represents a Nexus agent that must be integrated
during the onboarding flow. UUIDs are resolved automatically
from ONBOARDING_AGENT_UUIDS using the class name as key.
"""

import logging

from django.conf import settings

from retail.agents.domains.agent_integration.usecases.assign import AssignAgentUseCase
from retail.agents.domains.agent_management.models import Agent
from retail.projects.usecases.onboarding_agents.base import (
    ActiveAgent,
    AgentContext,
    PassiveAgent,
)
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


class OrdersAgentCommerceIO(PassiveAgent):
    name = "Orders Agent Commerce IO"


class FeedbackRecorder(PassiveAgent):
    name = "Feedback Recorder 2.0"


class ProductConcierge(PassiveAgent):
    name = "Product Concierge"


class PaymentAgent(PassiveAgent):
    name = "Payment Agent (without catalog)"


class SendCatalogAgent(PassiveAgent):
    name = "Send Catalog Agent"


class AbandonedCartAgent(ActiveAgent):
    """
    Active agent for abandoned cart notifications via WhatsApp Cloud.

    Uses AssignAgentUseCase to create IntegratedAgent, templates, and
    the default abandoned cart custom template. Requires app_uuid and
    channel_uuid in the AgentContext (set after wpp-cloud channel creation).
    """

    name = "Abandoned Cart"

    def __init__(self):
        abandoned_cart_uuid = getattr(settings, "ABANDONED_CART_AGENT_UUID", "")
        if abandoned_cart_uuid:
            self.uuid = abandoned_cart_uuid

    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        self._validate_uuid()
        self._validate_channel_context(context)

        try:
            agent = Agent.objects.get(uuid=self.uuid)
        except Agent.DoesNotExist:
            raise ValueError(
                f"Abandoned Cart Agent not found in database: uuid={self.uuid}"
            )

        all_template_uuids = list(agent.templates.values_list("uuid", flat=True))

        logger.info(
            f"Assigning Abandoned Cart agent for project={context.project_uuid} "
            f"app_uuid={context.app_uuid} channel_uuid={context.channel_uuid}"
        )

        use_case = AssignAgentUseCase()
        integrated_agent = use_case.execute(
            agent=agent,
            project_uuid=context.project_uuid,
            app_uuid=context.app_uuid,
            channel_uuid=context.channel_uuid,
            credentials={},
            include_templates=all_template_uuids,
        )

        integrated_agent.contact_percentage = 0
        integrated_agent.save(update_fields=["contact_percentage"])

        logger.info(
            f"Abandoned Cart agent assigned with contact_percentage=0: "
            f"integrated_agent={integrated_agent.uuid} "
            f"project={context.project_uuid}"
        )

        return {"integrated_agent_uuid": str(integrated_agent.uuid)}
