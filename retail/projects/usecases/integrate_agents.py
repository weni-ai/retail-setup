import logging
from typing import List

from retail.clients.nexus.client import NexusClient
from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.onboarding_agents.agent_mappings import (
    get_channel_agents,
)
from retail.projects.usecases.onboarding_agents.base import (
    AgentContext,
    OnboardingAgent,
)
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)

AGENT_PROGRESS_START = 75
AGENT_PROGRESS_END = 100


class AgentIntegrationError(Exception):
    """Raised when agent integration fails."""


class IntegrateAgentsUseCase:
    """
    Integrates onboarding agents into a project.

    The agent list is determined by the channel type stored in the
    onboarding config. Each agent instance knows how to integrate
    itself via its ``integrate(context, nexus_service)`` method.

    Progress: 75% -> 100%.
    """

    def __init__(self, nexus_client: NexusClientInterface = None):
        self.nexus_service = NexusService(nexus_client=nexus_client or NexusClient())

    def execute(self, vtex_account: str) -> None:
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise AgentIntegrationError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        project_uuid = str(onboarding.project.uuid)
        channels = (onboarding.config or {}).get("channels", {})
        channel_code = next(iter(channels), "wwc")

        agents = get_channel_agents(channel_code)

        if not agents:
            logger.info(
                f"No agents configured for channel '{channel_code}', "
                f"skipping integration."
            )
            onboarding.progress = AGENT_PROGRESS_END
            onboarding.save(update_fields=["progress"])
            return

        # Carries all data that at least one agent needs for integration;
        # each agent consumes only the fields relevant to its own flow.
        context = AgentContext(
            project_uuid=project_uuid,
            vtex_account=vtex_account,
        )

        self._integrate_agents(onboarding, context, agents)

    def _integrate_agents(
        self,
        onboarding: ProjectOnboarding,
        context: AgentContext,
        agents: List[OnboardingAgent],
    ) -> None:
        total = len(agents)
        progress_range = AGENT_PROGRESS_END - AGENT_PROGRESS_START

        for index, agent in enumerate(agents):
            result = agent.integrate(context, self.nexus_service)

            if result is not None:
                logger.info(
                    f"Agent {agent.name} ({agent.uuid}) integrated "
                    f"for project={context.project_uuid}"
                )
            else:
                logger.error(
                    f"Failed to integrate agent {agent.name} ({agent.uuid}) "
                    f"for project={context.project_uuid}"
                )

            onboarding.progress = AGENT_PROGRESS_START + int(
                ((index + 1) / total) * progress_range
            )
            onboarding.save(update_fields=["progress"])

        logger.info(
            f"Agent integration completed for project={context.project_uuid}: "
            f"{total} agents processed."
        )
