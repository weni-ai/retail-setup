import logging

from retail.clients.crawler.client import CrawlerClient
from retail.interfaces.clients.crawler.client import CrawlerClientInterface
from retail.projects.models import Project
from retail.services.crawler.service import CrawlerService

logger = logging.getLogger(__name__)


class DetectStorefrontTypeUseCase:
    """
    Detects the storefront technology for a store and persists it
    in the project config.

    Non-blocking by design: failures are logged but never propagated,
    so callers can fire-and-forget without risking the main flow.
    """

    def __init__(self, crawler_client: CrawlerClientInterface = None):
        self.crawler_service = CrawlerService(
            crawler_client=crawler_client or CrawlerClient()
        )

    def execute(self, project: Project, store_url: str) -> None:
        if project is None:
            return

        try:
            result = self.crawler_service.detect_storefront_type(store_url)
        except Exception:
            logger.exception(
                f"Unexpected error detecting storefront type "
                f"for project={project.uuid}"
            )
            return

        if result is None:
            logger.warning(
                f"Could not detect storefront type for project={project.uuid}"
            )
            return

        storefront_type = result.get("storefront_type")
        if not storefront_type:
            return

        config = project.config or {}
        config["storefront_type"] = storefront_type
        project.config = config
        project.save(update_fields=["config"])

        logger.info(
            f"Storefront type '{storefront_type}' stored "
            f"for project={project.uuid}"
        )
