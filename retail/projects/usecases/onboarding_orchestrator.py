import logging

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
)
from retail.projects.usecases.configure_one_click_payment import (
    ConfigureOneClickPaymentUseCase,
)
from retail.projects.usecases.integrate_agents import IntegrateAgentsUseCase
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed

logger = logging.getLogger(__name__)


NEXUS_CONFIG_START_PROGRESS = 10

# Channels that require the One-Click Payment configuration step.
# Kept as a registry so future channels can opt in (or out) without
# touching the orchestrator body.
CHANNELS_WITH_ONE_CLICK_PAYMENT = {"wpp-cloud"}


class OnboardingOrchestrator:
    """
    Orchestrates post-crawl configuration that runs INLINE in the main
    onboarding flow (right after the crawler is kicked off):

      1. Nexus manager configuration (10-75%) -- configures the agent
                                                  manager attributes ONLY.
                                                  Content upload happens
                                                  in background later, when
                                                  the crawl webhook arrives.
      2. One-Click Payment (wpp-cloud)        -- registers keys + creates
                                                  + publishes Meta Flow
                                                  (runs BEFORE agent
                                                  integration so the
                                                  One-Click Payment agent
                                                  can consume the published
                                                  flow_id as a credential)
      3. Agent integration (75-100%)          -- integrates Nexus agents
                                                  for the channel

    Channel creation runs before the crawl (see ``PreCrawlChannelUseCase``)
    so the short-lived Facebook ``auth_code`` is not exposed to the
    crawl's runtime. Both channels' ``app_uuid`` / ``flow_object_uuid``
    are already persisted by the time this orchestrator runs.

    Crawl + Nexus content upload run in the background and do NOT affect
    the main onboarding progress: the user-visible wizard completes once
    this orchestrator returns. The content upload to Nexus is dispatched
    by ``UpdateOnboardingProgressUseCase`` when the ``crawl.completed``
    webhook arrives.

    Each step is sequential. If any step fails, progress freezes
    at the last saved value and the error propagates.
    """

    def execute(self, vtex_account: str) -> None:
        logger.info(f"Starting post-crawl config for vtex_account={vtex_account}")

        try:
            self._mark_nexus_config_started(vtex_account)

            ConfigureAgentBuilderUseCase().execute(vtex_account)

            channel_code = self._resolve_channel_code(vtex_account)
            if channel_code in CHANNELS_WITH_ONE_CLICK_PAYMENT:
                ConfigureOneClickPaymentUseCase().execute(vtex_account)

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

    @staticmethod
    def _resolve_channel_code(vtex_account: str) -> str:
        """Resolves the channel code from the onboarding config."""
        onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
        channels = (onboarding.config or {}).get("channels", {})
        channel = next(iter(channels), None)

        if channel is None:
            raise ValueError(
                f"No channel configured in onboarding "
                f"for vtex_account={vtex_account}"
            )

        return channel
