import logging

from retail.projects.usecases.channel_usecase_resolver import (
    resolve_channel_usecase,
)

logger = logging.getLogger(__name__)


class PreCrawlChannelUseCase:
    """
    Runs the channel-specific configuration use case before the crawl.

    The Facebook Embedded Signup ``auth_code`` is short-lived, so the
    channel must be created (and the auth_code exchanged on the
    integrations-engine side) as early as possible — before the
    long-running crawl can expire it.

    The concrete use case (``ConfigureWPPCloudUseCase`` or
    ``ConfigureWWCUseCase``) is resolved from the channel stored in
    ``onboarding.config["channels"]`` and is responsible for setting
    ``current_step = "PROJECT_CONFIG"`` and driving its own progress.
    """

    def execute(self, vtex_account: str) -> None:
        channel_cls = resolve_channel_usecase(vtex_account)

        logger.info(
            f"Running pre-crawl channel setup: "
            f"vtex_account={vtex_account} usecase={channel_cls.__name__}"
        )

        channel_cls().execute(vtex_account)
