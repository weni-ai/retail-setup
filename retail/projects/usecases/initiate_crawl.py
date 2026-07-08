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

    Invoked by ``OnboardingOrchestrator`` as the first sub-phase of
    ``NEXUS_CONFIG``, after pre-crawl channel setup completes.
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
        """Propagates the store host to Connect.

        The host value is the ``crawl_url`` received from the storefront at
        start-setup; it is NOT fetched from VTEX here. The local
        ``Project.config["vtex_host_store"]`` is only persisted once Connect
        echoes it back via EDA, so this log trail is the source of truth for
        whether the outbound propagation happened.
        """
        logger.info(
            f"[vtex_host_store] Resolved store host for project={project.uuid} "
            f"vtex_account={project.vtex_account}: host={crawl_url!r}. "
            f"Sending to Connect."
        )
        try:
            self.connect_service.update_project_config(
                project_uuid=str(project.uuid),
                config={"vtex_host_store": crawl_url},
            )
        except Exception:
            logger.exception(
                f"[vtex_host_store] Failed to send to Connect for "
                f"project={project.uuid} vtex_account={project.vtex_account} "
                f"host={crawl_url!r}"
            )
            return

        logger.info(
            f"[vtex_host_store] Sent to Connect for project={project.uuid} "
            f"vtex_account={project.vtex_account} host={crawl_url!r}. "
            f"Awaiting EDA echo to persist locally."
        )
