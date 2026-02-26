import logging

from retail.projects.models import ProjectOnboarding
from retail.projects.tasks import acquire_task_lock, task_configure_nexus
from retail.projects.usecases.onboarding_dto import CrawlerWebhookDTO

logger = logging.getLogger(__name__)

COMPLETED_EVENT = "crawl.completed"
FAILED_EVENT = "crawl.failed"


class UpdateOnboardingProgressUseCase:
    """
    Processes webhook events coming from the Crawler MS.

    Each event type is handled by a dedicated method, keeping
    the orchestrator (execute) focused on routing only.
    """

    @staticmethod
    def execute(onboarding_uuid: str, dto: CrawlerWebhookDTO) -> ProjectOnboarding:
        """
        Routes the crawler webhook event to the appropriate handler.

        Args:
            onboarding_uuid: The ProjectOnboarding UUID from the webhook URL.
            dto: Event data received from the crawler webhook.

        Returns:
            The updated ProjectOnboarding instance.

        Raises:
            ProjectOnboarding.DoesNotExist: If no onboarding record is found.
        """
        onboarding = ProjectOnboarding.objects.get(
            uuid=onboarding_uuid,
        )

        if dto.event == COMPLETED_EVENT:
            return UpdateOnboardingProgressUseCase._handle_completed(onboarding, dto)

        if dto.event == FAILED_EVENT:
            return UpdateOnboardingProgressUseCase._handle_failed(onboarding, dto)

        return UpdateOnboardingProgressUseCase._handle_progress(onboarding, dto)

    @staticmethod
    def _handle_completed(
        onboarding: ProjectOnboarding, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
        """Marks crawl as successful and dispatches the NEXUS_CONFIG task."""
        onboarding.progress = 100
        onboarding.crawler_result = ProjectOnboarding.SUCCESS
        onboarding.save(update_fields=["progress", "crawler_result"])

        contents = dto.data.get("contents", [])
        vtex_account = onboarding.vtex_account

        logger.info(
            f"Crawler completed for onboarding={onboarding.uuid}. "
            f"Dispatching NEXUS_CONFIG with {len(contents)} content items."
        )

        if acquire_task_lock("configure_nexus", vtex_account):
            task_configure_nexus.delay(vtex_account, contents)
        else:
            logger.warning(
                f"Nexus config task already running for vtex_account={vtex_account}, "
                f"skipping dispatch."
            )

        return onboarding

    @staticmethod
    def _handle_failed(
        onboarding: ProjectOnboarding, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
        """Records the crawl failure."""
        onboarding.crawler_result = ProjectOnboarding.FAIL
        onboarding.save(update_fields=["crawler_result"])

        logger.error(
            f"Crawler failed for onboarding={onboarding.uuid}: "
            f"{dto.data.get('error', 'Unknown error')}"
        )
        return onboarding

    @staticmethod
    def _handle_progress(
        onboarding: ProjectOnboarding, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
        """Updates crawl progress when it has advanced."""
        if dto.progress > onboarding.progress:
            onboarding.progress = dto.progress
            onboarding.save(update_fields=["progress"])

        logger.info(
            f"Crawl progress for onboarding={onboarding.uuid}: "
            f"event={dto.event} progress={onboarding.progress}%"
        )
        return onboarding
