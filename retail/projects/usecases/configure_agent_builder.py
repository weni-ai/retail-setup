import logging

from retail.clients.nexus.client import NexusClient
from retail.interfaces.clients.nexus.client import NexusClientInterface
from retail.projects.usecases.agent_builder_helpers import (
    ensure_agent_manager_configured,
    load_onboarding_with_linked_project,
)
from retail.services.nexus.service import NexusService

logger = logging.getLogger(__name__)


MANAGER_DONE_PROGRESS = 75


class ConfigureAgentBuilderUseCase:
    """
    Inline (main-flow) configuration of the Nexus Agent Builder manager
    attributes.

    Invoked by ``OnboardingOrchestrator`` right after the crawler is
    kicked off. Configures the agent manager (name, goal, role,
    personality) using the project language for translation and bumps
    the onboarding progress to ``MANAGER_DONE_PROGRESS`` (75%).

    Does NOT upload any content -- the crawled content is uploaded
    asynchronously by ``UploadNexusContentsUseCase`` when the crawler's
    ``crawl.completed`` webhook arrives.
    """

    def __init__(
        self,
        nexus_client: NexusClientInterface = None,
    ):
        self.nexus_service = NexusService(nexus_client=nexus_client or NexusClient())

    def execute(self, vtex_account: str) -> None:
        """
        Args:
            vtex_account: The VTEX account identifier for the onboarding.

        Raises:
            ProjectNotLinkedError: If the onboarding has no project linked.
        """
        onboarding = load_onboarding_with_linked_project(vtex_account)
        project_uuid = str(onboarding.project.uuid)
        language = onboarding.project.language or ""

        ensure_agent_manager_configured(
            project_uuid, vtex_account, language, self.nexus_service
        )

        onboarding.progress = MANAGER_DONE_PROGRESS
        onboarding.save(update_fields=["progress"])
