"""
Active onboarding agents.

Passive agents are loaded dynamically from environment variables
(PASSIVE_AGENTS_WWC / PASSIVE_AGENTS_WPP_CLOUD) via agent_mappings.py.
Only active agents — which require complex integration logic — are
defined as explicit classes here.
"""

import logging

from django.conf import settings

from retail.agents.domains.agent_integration.usecases.assign import AssignAgentUseCase
from retail.agents.domains.agent_management.models import Agent
from retail.projects.usecases.onboarding_agents.base import (
    ActiveAgent,
    AgentContext,
)
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


WHATSAPP_CVV_FLOW_CREDENTIAL_NAME = "WHATSAPP_CVV_FLOW_ID"
WHATSAPP_CVV_FLOW_CREDENTIAL_LABEL = "WhatsApp CVV Flow ID"


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


class OneClickPaymentAgent(ActiveAgent):
    """
    Active agent for the One-Click Payment flow on WhatsApp Cloud.

    Integration steps:

    1. Standard Nexus app-assign (same call PassiveAgent makes).
    2. Bind the ``wpp_flow_uuid`` credential on the agent — the value
       is the Meta Flow id created earlier by
       ``ConfigureOneClickPaymentUseCase`` and passed through the
       AgentContext.

    Instantiated by ``get_channel_agents`` when the env JSON for the
    channel contains the code registered in ``PASSIVE_AGENT_OVERRIDES``
    (so the UUID still comes from ``PASSIVE_AGENTS_WPP_CLOUD`` like
    every other agent).
    """

    name = "One Click Payment"

    def __init__(self, uuid: str = "", name: str = ""):
        if uuid:
            self.uuid = uuid
        if name:
            self.name = name

    def integrate(self, context: AgentContext, nexus_service: NexusService) -> dict:
        self._validate_uuid()
        self._validate_flow_id(context)

        assign_response = nexus_service.integrate_agent(context.project_uuid, self.uuid)
        if assign_response is None:
            return None

        credentials_response = nexus_service.create_agent_credentials(
            project_uuid=context.project_uuid,
            agent_uuid=self.uuid,
            credentials=[self._build_cvv_flow_credential(context.flow_id)],
        )
        if credentials_response is None:
            return None

        logger.info(
            f"One-Click Payment agent {self.uuid} integrated with "
            f"{WHATSAPP_CVV_FLOW_CREDENTIAL_NAME} credential for "
            f"project={context.project_uuid}"
        )

        return {
            "agent_assignment": assign_response,
            "credentials": credentials_response,
        }

    @staticmethod
    def _build_cvv_flow_credential(flow_id: str) -> dict:
        return {
            "name": WHATSAPP_CVV_FLOW_CREDENTIAL_NAME,
            "label": WHATSAPP_CVV_FLOW_CREDENTIAL_LABEL,
            "is_confidential": True,
            "value": flow_id,
        }

    def _validate_flow_id(self, context: AgentContext) -> None:
        if not context.flow_id:
            raise ValueError(
                f"One-Click Payment agent '{self.name}' requires "
                f"context.flow_id. Ensure ConfigureOneClickPaymentUseCase "
                f"ran before agent integration for the wpp-cloud channel."
            )
