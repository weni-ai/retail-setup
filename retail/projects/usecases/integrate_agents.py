import logging
from typing import List, Set

from retail.agents.domains.agent_integration.models import IntegratedAgent
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

    Agents already integrated in the project are detected via the
    Nexus list and skipped to avoid duplicates.

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

        channel_config = channels.get(channel_code, {})
        integrated_uuids = self._get_integrated_agent_uuids(project_uuid)

        context = AgentContext(
            project_uuid=project_uuid,
            vtex_account=vtex_account,
            app_uuid=channel_config.get("app_uuid"),
            channel_uuid=channel_config.get("flow_object_uuid"),
        )

        self._integrate_agents(onboarding, context, agents, integrated_uuids)

    def _get_integrated_agent_uuids(self, project_uuid: str) -> Set[str]:
        """
        Fetches UUIDs of agents already integrated in the project.

        Combines both sources:
          - Nexus (passive agents via app-assign)
          - Retail DB (active agents via IntegratedAgent)
        """
        nexus_uuids = self._get_nexus_integrated_uuids(project_uuid)
        retail_uuids = self._get_retail_integrated_uuids(project_uuid)
        return nexus_uuids | retail_uuids

    def _get_nexus_integrated_uuids(self, project_uuid: str) -> Set[str]:
        """Fetches UUIDs of passive agents integrated via Nexus."""
        response = self.nexus_service.list_integrated_agents(project_uuid)
        if not response:
            return set()

        agents = response if isinstance(response, list) else response.get("results", [])
        return {str(agent.get("uuid", "")) for agent in agents if agent.get("uuid")}

    @staticmethod
    def _get_retail_integrated_uuids(project_uuid: str) -> Set[str]:
        """Fetches UUIDs of active agents integrated via Retail."""
        return {
            str(uuid)
            for uuid in IntegratedAgent.objects.filter(
                project__uuid=project_uuid,
                is_active=True,
            )
            .values_list("agent__uuid", flat=True)
            .distinct()
        }

    def _integrate_agents(
        self,
        onboarding: ProjectOnboarding,
        context: AgentContext,
        agents: List[OnboardingAgent],
        integrated_uuids: Set[str],
    ) -> None:
        total = len(agents)
        progress_range = AGENT_PROGRESS_END - AGENT_PROGRESS_START

        for index, agent in enumerate(agents):
            if agent.uuid in integrated_uuids:
                logger.info(
                    f"Agent {agent.name} ({agent.uuid}) already integrated "
                    f"for project={context.project_uuid}, skipping."
                )
                onboarding.progress = AGENT_PROGRESS_START + int(
                    ((index + 1) / total) * progress_range
                )
                onboarding.save(update_fields=["progress"])
                continue

            result = agent.integrate(context, self.nexus_service)

            if result is None:
                raise AgentIntegrationError(
                    f"Failed to integrate agent {agent.name} ({agent.uuid}) "
                    f"for project={context.project_uuid}"
                )

            logger.info(
                f"Agent {agent.name} ({agent.uuid}) integrated "
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
