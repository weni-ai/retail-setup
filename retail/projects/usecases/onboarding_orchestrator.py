import logging

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
)
from retail.projects.usecases.integrate_agents import IntegrateAgentsUseCase
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed

logger = logging.getLogger(__name__)


NEXUS_CONFIG_START_PROGRESS = 10


class OnboardingOrchestrator:
    """
    Orchestrates post-crawl configuration:
      1. Nexus manager + upload (20-75%) -- configures agent and uploads content
      2. Agent integration (75-100%)     -- integrates Nexus agents for the channel

    Channel creation runs before the crawl (see ``PreCrawlChannelUseCase``)
    so the short-lived Facebook ``auth_code`` is not exposed to the
    crawl's runtime. Both channels' ``app_uuid`` / ``flow_object_uuid``
    are already persisted by the time this orchestrator runs.

    Each step is sequential. If any step fails, progress freezes
    at the last saved value and the error propagates.
    """

    def execute(self, vtex_account: str, contents: list) -> None:
        logger.info(f"Starting post-crawl config for vtex_account={vtex_account}")

        try:
            self._mark_nexus_config_started(vtex_account)

            ConfigureAgentBuilderUseCase().execute(vtex_account, contents)

            IntegrateAgentsUseCase().execute(vtex_account)
        except Exception as exc:
            mark_onboarding_failed(vtex_account, str(exc))
            raise

        logger.info(f"NEXUS_CONFIG completed for vtex_account={vtex_account}")

    @staticmethod
    def _mark_nexus_config_started(vtex_account: str) -> None:
        """Transitions the onboarding into the NEXUS_CONFIG step."""
        onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
        onboarding.current_step = "NEXUS_CONFIG"
        onboarding.progress = NEXUS_CONFIG_START_PROGRESS
        onboarding.save(update_fields=["current_step", "progress"])
