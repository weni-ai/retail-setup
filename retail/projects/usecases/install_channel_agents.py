import logging
from typing import Callable, Optional, Set

from retail.clients.integrations.client import IntegrationsClient
from retail.clients.nexus.client import NexusClient
from retail.interfaces.clients.integrations.interface import IntegrationsClientInterface
from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.configure_wwc import (
    WWC_CREATION_CONFIG,
    build_wwc_channel_config,
)
from retail.projects.usecases.onboarding_agents.agent_mappings import (
    SUPPORTED_CHANNELS,
    get_channel_agents,
)
from retail.projects.usecases.onboarding_agents.base import (
    AgentContext,
    OnboardingAgent,
)
from retail.projects.usecases.onboarding_agents.integrated_agent_lookup import (
    get_integrated_agent_uuids,
)
from retail.projects.usecases.onboarding_dto import InstallChannelAgentsDTO
from retail.services.integrations.service import IntegrationsService
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)

CHANNEL_CREATION_CONFIGS: dict[str, dict] = {
    "wwc": WWC_CREATION_CONFIG,
}

CHANNEL_CONFIGURE_BUILDERS: dict[str, Callable[[str], dict]] = {
    "wwc": build_wwc_channel_config,
}


class InstallChannelAgentsError(Exception):
    """Raised when channel agent installation fails."""


class InstallChannelAgentsUseCase:
    """
    Installs agents for a specific channel on an existing onboarding.

    Used when a store has completed onboarding for one channel (e.g. WWC)
    and wants to add another (e.g. WPP-Cloud).

    Flow:
      1. Creates the channel via Integrations API.
      2. Configures the channel when required (e.g. WWC needs colors/translations).
      3. Stores the channel in the onboarding config.
      4. Integrates agents mapped to that channel, skipping any
         that are already integrated in the project.
    """

    def __init__(
        self,
        nexus_client: Optional[NexusClientInterface] = None,
        integrations_client: Optional[IntegrationsClientInterface] = None,
    ):
        self.nexus_service = NexusService(nexus_client=nexus_client or NexusClient())
        self.integrations_service = IntegrationsService(
            client=integrations_client or IntegrationsClient()
        )

    def execute(self, dto: InstallChannelAgentsDTO) -> None:
        if dto.channel not in SUPPORTED_CHANNELS:
            raise ValueError(
                f"Unsupported channel '{dto.channel}'. "
                f"Supported: {SUPPORTED_CHANNELS}"
            )

        onboarding = self._load_onboarding(dto.vtex_account)
        project_uuid = str(onboarding.project.uuid)
        language = onboarding.project.language or ""

        logger.info(
            f"Starting channel agent installation: "
            f"channel={dto.channel} vtex_account={dto.vtex_account}"
        )

        creation_config = CHANNEL_CREATION_CONFIGS.get(dto.channel, dto.channel_data)
        app_data = self._create_channel(dto.channel, project_uuid, creation_config)
        app_uuid = app_data.get("uuid", "")

        self._configure_channel(dto.channel, app_uuid, project_uuid, language)
        self._persist_channel(onboarding, dto.channel, app_uuid)

        agents = get_channel_agents(dto.channel)

        if not agents:
            logger.info(
                f"No agents configured for channel '{dto.channel}', "
                f"skipping integration."
            )
            return

        integrated_uuids = get_integrated_agent_uuids(project_uuid, self.nexus_service)

        context = AgentContext(
            project_uuid=project_uuid,
            vtex_account=dto.vtex_account,
        )

        self._integrate_agents(agents, context, integrated_uuids)

    def _load_onboarding(self, vtex_account: str) -> ProjectOnboarding:
        """Loads and validates the onboarding record has a linked project."""
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account
        )

        if onboarding.project is None:
            raise InstallChannelAgentsError(
                f"Onboarding {onboarding.uuid} has no project linked yet."
            )

        return onboarding

    def _create_channel(
        self, channel: str, project_uuid: str, channel_data: dict
    ) -> dict:
        """Creates the channel app via Integrations API."""
        response = self.integrations_service.create_channel_app(
            channel, project_uuid, channel_data
        )

        if response is None:
            raise InstallChannelAgentsError(
                f"Failed to create {channel} channel for project={project_uuid}"
            )

        logger.info(
            f"Channel '{channel}' created for project={project_uuid}: "
            f"app_uuid={response.get('uuid')}"
        )
        return response

    def _configure_channel(
        self, channel: str, app_uuid: str, project_uuid: str, language: str
    ) -> None:
        """Applies channel-specific configuration when required (e.g. WWC)."""
        config_builder = CHANNEL_CONFIGURE_BUILDERS.get(channel)
        if not config_builder:
            return

        config = config_builder(language)
        response = self.integrations_service.configure_channel_app(
            channel, app_uuid, config
        )

        if response is None:
            raise InstallChannelAgentsError(
                f"Failed to configure {channel} app={app_uuid} "
                f"for project={project_uuid}"
            )

        logger.info(
            f"Channel '{channel}' configured for project={project_uuid}: "
            f"app_uuid={app_uuid}"
        )

    @staticmethod
    def _persist_channel(
        onboarding: ProjectOnboarding, channel: str, app_uuid: str
    ) -> None:
        """Stores the channel app UUID in the onboarding config."""
        config = onboarding.config or {}
        channels = config.setdefault("channels", {})
        channels[channel] = {**channels.get(channel, {}), "app_uuid": app_uuid}
        onboarding.config = config
        onboarding.save(update_fields=["config"])

        logger.info(
            f"Channel '{channel}' stored in onboarding config: "
            f"vtex_account={onboarding.vtex_account} app_uuid={app_uuid}"
        )

    def _integrate_agents(
        self,
        agents: list[OnboardingAgent],
        context: AgentContext,
        integrated_uuids: Set[str],
    ) -> None:
        """Integrates agents, skipping those already integrated."""
        integrated_count = 0
        skipped_count = 0

        for agent in agents:
            if agent.uuid in integrated_uuids:
                logger.info(
                    f"Agent {agent.name} ({agent.uuid}) already integrated "
                    f"for project={context.project_uuid}, skipping."
                )
                skipped_count += 1
                continue

            result = agent.integrate(context, self.nexus_service)

            if result is None:
                raise InstallChannelAgentsError(
                    f"Failed to integrate agent {agent.name} ({agent.uuid}) "
                    f"for project={context.project_uuid}"
                )

            logger.info(
                f"Agent {agent.name} ({agent.uuid}) integrated "
                f"for project={context.project_uuid}"
            )
            integrated_count += 1

        logger.info(
            f"Channel agent installation completed for "
            f"project={context.project_uuid}: "
            f"{integrated_count} integrated, {skipped_count} skipped."
        )
