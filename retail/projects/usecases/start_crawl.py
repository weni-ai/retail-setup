import logging

from django.conf import settings

from retail.clients.crawler.client import CrawlerClient
from retail.interfaces.clients.crawler.client import CrawlerClientInterface
from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.manager_defaults import get_manager_defaults
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed
from retail.projects.usecases.onboarding_defaults import get_instructions
from retail.services.crawler.service import CrawlerService

logger = logging.getLogger(__name__)


class CrawlerStartError(Exception):
    """Raised when the Crawler MS fails to start."""


class StartCrawlUseCase:
    """
    Starts the crawl by calling the Crawler MS.

    Sets current_step to CRAWL, resets progress, builds the webhook URL
    using the onboarding UUID, and forwards the request to the crawler.
    """

    def __init__(
        self,
        crawler_client: CrawlerClientInterface = None,
    ):
        self.crawler_service = CrawlerService(
            crawler_client=crawler_client or CrawlerClient()
        )

    def execute(self, vtex_account: str, crawl_url: str) -> None:
        """
        Triggers the crawl for the given vtex_account.

        Args:
            vtex_account: The VTEX account identifier.
            crawl_url: The store URL to crawl.

        Raises:
            CrawlerStartError: If the crawler fails to start.
        """
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account,
        )

        onboarding.current_step = "CRAWL"
        onboarding.progress = 0
        onboarding.save(update_fields=["current_step", "progress"])

        onboarding_uuid = str(onboarding.uuid)
        language = onboarding.project.language or "" if onboarding.project else ""
        webhook_url = self._build_webhook_url(onboarding_uuid)
        project_context = self._build_project_context(vtex_account, language)

        logger.info(
            f"Starting crawler for vtex_account={vtex_account} "
            f"crawl_url={crawl_url} webhook_url={webhook_url} "
            f"project_context={project_context}"
        )

        response = self.crawler_service.start_crawling(
            crawl_url, webhook_url, project_context
        )

        if response is None:
            onboarding.crawler_result = ProjectOnboarding.FAIL
            onboarding.save(update_fields=["crawler_result"])

            error_msg = "Failed to communicate with the Crawler service."
            mark_onboarding_failed(vtex_account, error_msg)
            raise CrawlerStartError(error_msg)

        logger.info(
            f"Crawl started for vtex_account={vtex_account} crawl_url={crawl_url}"
        )

    @staticmethod
    def _build_webhook_url(onboarding_uuid: str) -> str:
        """Builds the webhook URL using the onboarding UUID."""
        base = settings.DOMAIN.rstrip("/")
        return f"{base}/api/onboard/{onboarding_uuid}/webhook/"

    @staticmethod
    def _build_project_context(vtex_account: str, language: str) -> dict:
        """
        Builds the project context payload for the crawler.

        The objective is the translated manager goal for the project language.
        Instructions are also resolved by language.
        """
        defaults = get_manager_defaults(language)
        return {
            "account_name": vtex_account,
            "objective": defaults["goal"],
            "instructions": get_instructions(language),
        }
