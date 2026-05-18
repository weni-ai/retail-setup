import logging
from typing import Optional

from retail.projects.models import Project
from retail.projects.usecases.detect_storefront_type import (
    DetectStorefrontTypeUseCase,
)
from retail.projects.usecases.start_crawl import StartCrawlUseCase
from retail.services.connect.service import ConnectService

logger = logging.getLogger(__name__)


class InitiateCrawlUseCase:
    """
    Runs the full crawl initiation sequence once a project is linked:
      1. Sends the store URL to Connect (non-blocking).
      2. Starts the crawl via the Crawler MS (critical).
      3. Detects the storefront type (non-blocking).

    Invoked by ``task_setup_channel_and_start_crawl`` after the pre-crawl
    channel setup completes successfully.
    """

    def __init__(self, connect_service: Optional[ConnectService] = None):
        self.connect_service = connect_service or ConnectService()
        self.start_crawl_usecase = StartCrawlUseCase()
        self.detect_storefront_usecase = DetectStorefrontTypeUseCase()

    def execute(self, project: Project, vtex_account: str, crawl_url: str) -> None:
        self._send_vtex_host_store(project, crawl_url)
        self.start_crawl_usecase.execute(vtex_account, crawl_url)
        self.detect_storefront_usecase.execute(project, crawl_url)

    def _send_vtex_host_store(self, project: Project, crawl_url: str) -> None:
        try:
            self.connect_service.update_project_config(
                project_uuid=str(project.uuid),
                config={"vtex_host_store": crawl_url},
            )
        except Exception:
            logger.exception(
                f"Failed to send vtex_host_store to Connect "
                f"for project={project.uuid}"
            )
