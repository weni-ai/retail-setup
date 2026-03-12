import logging
from typing import Optional

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.tasks import task_wait_and_start_crawl
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed
from retail.projects.usecases.onboarding_agents.agent_mappings import SUPPORTED_CHANNELS
from retail.projects.usecases.onboarding_dto import StartOnboardingDTO
from retail.projects.usecases.start_crawl import StartCrawlUseCase
from retail.services.connect.service import ConnectService

logger = logging.getLogger(__name__)


class StartOnboardingUseCase:
    """
    Initiates the crawl step of the onboarding process.

    If the project is already linked (via EDA), the crawl starts
    immediately. Otherwise, a Celery task is scheduled to wait
    until the project is linked and then start the crawl.
    """

    def __init__(self, connect_service: Optional[ConnectService] = None):
        self.start_crawl_usecase = StartCrawlUseCase()
        self.connect_service = connect_service or ConnectService()

    def execute(self, dto: StartOnboardingDTO) -> None:
        """
        Creates/gets the ProjectOnboarding record and decides whether
        to start crawling now or schedule a wait task.

        Args:
            dto: Contains vtex_account and crawl_url.

        Raises:
            CrawlerStartError: If the crawler fails to start (immediate mode).
        """
        onboarding, created = ProjectOnboarding.objects.get_or_create(
            vtex_account=dto.vtex_account,
        )

        if not created:
            self._reset_onboarding(onboarding)

        if dto.channel not in SUPPORTED_CHANNELS:
            mark_onboarding_failed(
                dto.vtex_account,
                f"Unsupported channel '{dto.channel}'. "
                f"Supported: {SUPPORTED_CHANNELS}",
            )
            raise ValueError(
                f"Unsupported channel '{dto.channel}'. "
                f"Supported: {SUPPORTED_CHANNELS}"
            )

        config = onboarding.config or {}
        channels = config.setdefault("channels", {})
        channels.setdefault(dto.channel, {})
        onboarding.config = config
        onboarding.save(update_fields=["config"])

        try:
            self._try_link_project(onboarding)
        except Exception as exc:
            mark_onboarding_failed(dto.vtex_account, str(exc))
            raise

        if onboarding.project is not None:
            self._send_vtex_host_store(onboarding.project, dto.crawl_url)
            self.start_crawl_usecase.execute(dto.vtex_account, dto.crawl_url)
            return

        task_wait_and_start_crawl.delay(dto.vtex_account, dto.crawl_url)

        logger.info(
            f"Project not linked yet for vtex_account={dto.vtex_account}. "
            f"Scheduled wait task for crawl_url={dto.crawl_url}"
        )

    @staticmethod
    def _reset_onboarding(onboarding: ProjectOnboarding) -> None:
        """Resets transient fields so a new crawl cycle starts clean."""
        onboarding.progress = 0
        onboarding.crawler_result = None
        onboarding.completed = False
        onboarding.failed = False
        onboarding.current_step = ""
        onboarding.save(
            update_fields=[
                "progress",
                "crawler_result",
                "completed",
                "failed",
                "current_step",
            ]
        )

    @staticmethod
    def _try_link_project(onboarding: ProjectOnboarding) -> None:
        """
        If no project is linked yet, tries to find the unique one
        by vtex_account. Raises if more than one project matches,
        since the business rule is 1 vtex_account → 1 project.
        """
        if onboarding.project is not None:
            return

        try:
            project = Project.objects.get(vtex_account=onboarding.vtex_account)
        except Project.DoesNotExist:
            return
        except Project.MultipleObjectsReturned:
            logger.error(
                f"Multiple projects found for vtex_account={onboarding.vtex_account}. "
                f"Expected exactly one. Data integrity issue."
            )
            raise

        onboarding.project = project
        onboarding.save(update_fields=["project"])

    def _send_vtex_host_store(self, project: Project, crawl_url: str) -> None:
        """Sends the crawl URL as vtex_host_store to Connect. Failures are
        logged but do not interrupt the onboarding flow."""
        try:
            self.connect_service.set_vtex_host_store(
                project_uuid=str(project.uuid),
                vtex_host_store=crawl_url,
            )
        except Exception:
            logger.exception(
                f"Failed to send vtex_host_store to Connect for "
                f"project={project.uuid}"
            )
