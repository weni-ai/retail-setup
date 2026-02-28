import logging
from typing import Type

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
)
from retail.projects.usecases.configure_wwc import ConfigureWWCUseCase
from retail.projects.usecases.integrate_agents import IntegrateAgentsUseCase
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed

logger = logging.getLogger(__name__)

CHANNEL_USECASES = {
    "wwc": ConfigureWWCUseCase,
}


class OnboardingOrchestrator:
    """
    Orchestrates post-crawl configuration:
      1. Channel creation (0-25%)   -- dispatches to the channel-specific use case
      2. Nexus manager + upload (25-75%) -- configures agent and uploads content
      3. Agent integration (75-100%)     -- integrates Nexus agents for the channel

    Each step is sequential. If any step fails, progress freezes
    at the last saved value and the error propagates.
    """

    def execute(self, vtex_account: str, contents: list) -> None:
        logger.info(f"Starting post-crawl config for vtex_account={vtex_account}")

        try:
            channel_cls = self._resolve_channel_usecase(vtex_account)
            channel_cls().execute(vtex_account)

            ConfigureAgentBuilderUseCase().execute(vtex_account, contents)

            IntegrateAgentsUseCase().execute(vtex_account)
        except Exception as exc:
            mark_onboarding_failed(vtex_account, str(exc))
            raise

        logger.info(f"NEXUS_CONFIG completed for vtex_account={vtex_account}")

    @staticmethod
    def _resolve_channel_usecase(vtex_account: str) -> Type:
        """Resolves the channel use case class from the onboarding config."""
        onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
        channels = (onboarding.config or {}).get("channels", {})
        channel = next(iter(channels), None)

        if channel is None:
            raise ValueError(
                f"No channel configured in onboarding "
                f"for vtex_account={vtex_account}"
            )

        usecase_cls = CHANNEL_USECASES.get(channel)
        if usecase_cls is None:
            raise ValueError(
                f"No channel use case registered for '{channel}'. "
                f"Supported: {list(CHANNEL_USECASES.keys())}"
            )
        return usecase_cls
