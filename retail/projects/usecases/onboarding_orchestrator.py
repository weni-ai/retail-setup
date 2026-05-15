import logging

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
)
from retail.projects.usecases.configure_one_click_payment import (
    ConfigureOneClickPaymentUseCase,
)
from retail.projects.usecases.configure_wwc import ConfigureWWCUseCase
from retail.projects.usecases.configure_wpp_cloud import ConfigureWPPCloudUseCase
from retail.projects.usecases.integrate_agents import IntegrateAgentsUseCase
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed

logger = logging.getLogger(__name__)

CHANNEL_USECASES = {
    "wwc": ConfigureWWCUseCase,
    "wpp-cloud": ConfigureWPPCloudUseCase,
}

# Channels that require the One-Click Payment configuration step at
# the end of the onboarding. Kept as a registry so future channels can
# opt in (or out) without touching the orchestrator body.
CHANNELS_WITH_ONE_CLICK_PAYMENT = {"wpp-cloud"}


class OnboardingOrchestrator:
    """
    Orchestrates post-crawl configuration:
      1. Channel creation (10-20%)       -- dispatches to the channel-specific use case
      2. Nexus manager + upload (20-75%) -- configures agent and uploads content
      3. Agent integration (75-100%)     -- integrates Nexus agents for the channel
      4. One-Click Payment (wpp-cloud)   -- registers keys + Flow with Meta and payment-ms

    Each step is sequential. If any step fails, progress freezes
    at the last saved value and the error propagates.
    """

    def execute(self, vtex_account: str, contents: list) -> None:
        logger.info(f"Starting post-crawl config for vtex_account={vtex_account}")

        try:
            channel_code = self._resolve_channel_code(vtex_account)
            CHANNEL_USECASES[channel_code]().execute(vtex_account)

            ConfigureAgentBuilderUseCase().execute(vtex_account, contents)

            IntegrateAgentsUseCase().execute(vtex_account)

            if channel_code in CHANNELS_WITH_ONE_CLICK_PAYMENT:
                ConfigureOneClickPaymentUseCase().execute(vtex_account)
        except Exception as exc:
            mark_onboarding_failed(vtex_account, str(exc))
            raise

        logger.info(f"NEXUS_CONFIG completed for vtex_account={vtex_account}")

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

        if channel not in CHANNEL_USECASES:
            raise ValueError(
                f"No channel use case registered for '{channel}'. "
                f"Supported: {list(CHANNEL_USECASES.keys())}"
            )

        return channel
