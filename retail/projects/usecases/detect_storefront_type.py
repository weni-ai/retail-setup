import logging

from retail.clients.connect.client import ConnectClient
from retail.clients.crawler.client import CrawlerClient
from retail.interfaces.clients.connect.interface import ConnectClientInterface
from retail.interfaces.clients.crawler.client import CrawlerClientInterface
from retail.projects.models import Project
from retail.services.connect.service import ConnectService
from retail.services.crawler.service import CrawlerService

logger = logging.getLogger(__name__)


class DetectStorefrontTypeUseCase:
    """
    Detects the storefront technology for a store and sends it
    to Connect so it flows back via EDA into the local project config.

    Non-blocking by design: failures are logged but never propagated,
    so callers can fire-and-forget without risking the main flow.
    """

    def __init__(
        self,
        crawler_client: CrawlerClientInterface = None,
        connect_client: ConnectClientInterface = None,
    ):
        self.crawler_service = CrawlerService(
            crawler_client=crawler_client or CrawlerClient()
        )
        self.connect_service = ConnectService(
            connect_client=connect_client or ConnectClient()
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

        try:
            self.connect_service.update_project_config(
                project_uuid=str(project.uuid),
                config={"storefront_type": storefront_type},
            )
        except Exception:
            logger.exception(
                f"Failed to send storefront_type to Connect "
                f"for project={project.uuid}"
            )
            return

        logger.info(
            f"Storefront type '{storefront_type}' sent to Connect "
            f"for project={project.uuid}"
        )
