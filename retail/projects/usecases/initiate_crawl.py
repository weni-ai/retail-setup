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
      1. Persists the store URL locally (for synchronous onboarding steps).
      2. Sends the store URL to Connect (non-blocking).
      3. Starts the crawl via the Crawler MS (critical).
      4. Detects the storefront type (non-blocking).

    Invoked by ``OnboardingOrchestrator`` as the first sub-phase of
    ``NEXUS_CONFIG``, after pre-crawl channel setup completes.
    """

    def __init__(self, connect_service: Optional[ConnectService] = None):
        self.connect_service = connect_service or ConnectService()
        self.start_crawl_usecase = StartCrawlUseCase()
        self.detect_storefront_usecase = DetectStorefrontTypeUseCase()

    def execute(self, project: Project, vtex_account: str, crawl_url: str) -> None:
        self._persist_vtex_host_store(project, crawl_url)
        self._send_vtex_host_store_to_connect(project, crawl_url)
        self.start_crawl_usecase.execute(vtex_account, crawl_url)
        self.detect_storefront_usecase.execute(project, crawl_url)

    def _persist_vtex_host_store(self, project: Project, crawl_url: str) -> None:
        """Persist the store URL locally so downstream onboarding steps can use it.

        Agent assignment (abandoned cart template) runs in the same synchronous
        NEXUS_CONFIG pipeline and must not depend on the async Connect → EDA
        round-trip. The EDA echo later confirms or updates this value.
        """
        config = project.config or {}
        config["vtex_host_store"] = crawl_url
        project.config = config
        project.save(update_fields=["config"])

        logger.info(
            f"[vtex_host_store] Persisted locally for project={project.uuid} "
            f"vtex_account={project.vtex_account}: host={crawl_url!r}"
        )

    def _send_vtex_host_store_to_connect(
        self, project: Project, crawl_url: str
    ) -> None:
        """Propagates the store host to Connect for cross-service sync."""
        logger.info(
            f"[vtex_host_store] Sending store host to Connect for "
            f"project={project.uuid} vtex_account={project.vtex_account}: "
            f"host={crawl_url!r}"
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
            f"EDA echo will confirm or update the local value."
        )
