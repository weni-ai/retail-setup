import logging
from typing import Type

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.configure_wpp_cloud import ConfigureWPPCloudUseCase
from retail.projects.usecases.configure_wwc import ConfigureWWCUseCase

logger = logging.getLogger(__name__)


CHANNEL_USECASES = {
    "wwc": ConfigureWWCUseCase,
    "wpp-cloud": ConfigureWPPCloudUseCase,
}


def resolve_channel_usecase(vtex_account: str) -> Type:
    """
    Resolves the channel use case class registered for the channel
    stored in the onboarding config.

    The channel is set by ``StartSetupUseCase`` when the front-end
    selects a channel and is later consumed by both the pre-crawl
    channel setup task and the post-crawl orchestrator (for agent
    integration lookups).

    Raises:
        ValueError: If no channel is configured or the channel is
            not registered in ``CHANNEL_USECASES``.
    """
    onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
    channels = (onboarding.config or {}).get("channels", {})
    channel = next(iter(channels), None)

    if channel is None:
        raise ValueError(
            f"No channel configured in onboarding " f"for vtex_account={vtex_account}"
        )

    usecase_cls = CHANNEL_USECASES.get(channel)
    if usecase_cls is None:
        raise ValueError(
            f"No channel use case registered for '{channel}'. "
            f"Supported: {list(CHANNEL_USECASES.keys())}"
        )
    return usecase_cls
