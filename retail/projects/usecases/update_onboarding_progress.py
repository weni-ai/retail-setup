import logging
from typing import Optional

from retail.projects.models import ProjectOnboarding
from retail.projects.tasks import (
    UPLOAD_NEXUS_LOCK_NAME,
    acquire_task_lock,
    task_upload_nexus_contents,
)
from retail.projects.usecases.onboarding_dto import CrawlerWebhookDTO
from retail.projects.usecases.save_background_failure import (
    SaveBackgroundFailureUseCase,
)
from retail.services.connect.service import ConnectService

logger = logging.getLogger(__name__)

COMPLETED_EVENT = "crawl.completed"
FAILED_EVENT = "crawl.failed"
URL_REDIRECTED_EVENT = "crawl.url_redirected"


class UpdateOnboardingProgressUseCase:
    """
    Processes webhook events coming from the Crawler MS.

    Each event type is handled by a dedicated method, keeping
    the orchestrator (execute) focused on routing only.
    """

    def __init__(self, connect_service: Optional[ConnectService] = None):
        self.connect_service = connect_service or ConnectService()

    def execute(
        self, onboarding_uuid: str, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
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
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            uuid=onboarding_uuid,
        )

        if dto.event == COMPLETED_EVENT:
            return self._handle_completed(onboarding, dto)

        if dto.event == FAILED_EVENT:
            return self._handle_failed(onboarding, dto)

        if dto.event == URL_REDIRECTED_EVENT:
            return self._handle_url_redirected(onboarding, dto)

        return self._handle_progress(onboarding, dto)

    @staticmethod
    def _handle_completed(
        onboarding: ProjectOnboarding, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
        """
        Records the crawl as successful and dispatches the background
        Nexus content upload.

        Does NOT touch ``onboarding.progress`` -- by the time this
        webhook arrives the main wizard may already be at
        ``NEXUS_CONFIG`` 100%, and pushing the bar back to 100 (or any
        value) would conflict with the inline orchestrator's writes.
        """
        onboarding.crawler_result = ProjectOnboarding.SUCCESS
        onboarding.save(update_fields=["crawler_result"])

        contents = dto.data.get("contents", [])
        vtex_account = onboarding.vtex_account

        logger.info(
            f"Crawler completed for onboarding={onboarding.uuid}. "
            f"Dispatching background nexus upload with {len(contents)} content items."
        )

        if acquire_task_lock(UPLOAD_NEXUS_LOCK_NAME, vtex_account):
            task_upload_nexus_contents.delay(vtex_account, contents)
        else:
            logger.warning(
                f"Nexus upload task already running for vtex_account={vtex_account}, "
                f"skipping dispatch."
            )

        return onboarding

    @staticmethod
    def _handle_failed(
        onboarding: ProjectOnboarding, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
        """
        Records a soft crawl failure.

        Does NOT flip ``onboarding.failed`` -- the main onboarding is
        decoupled from the background crawl outcome. The failure is
        persisted under ``config["background_error"]`` for ops
        visibility, and ``crawler_result`` is set to ``FAIL``.
        """
        onboarding.crawler_result = ProjectOnboarding.FAIL
        onboarding.save(update_fields=["crawler_result"])

        error_msg = dto.data.get("error", "Unknown error")
        SaveBackgroundFailureUseCase.execute(
            onboarding.vtex_account, "crawl", error_msg
        )
        logger.warning(
            f"Background crawl failed for onboarding={onboarding.uuid}: {error_msg}"
        )
        return onboarding

    def _handle_url_redirected(
        self, onboarding: ProjectOnboarding, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
        """
        Persists the resolved store URL locally and propagates it to Connect.

        Triggered when the original URL failed but a variant (e.g. with `www.`)
        succeeded. The resolved URL becomes the canonical store URL going forward.
        """
        resolved_url = dto.data.get("resolved_url")
        original_url = dto.data.get("original_url")

        if not resolved_url:
            logger.warning(
                f"[url_redirected] Missing resolved_url in webhook payload for "
                f"onboarding={onboarding.uuid}. Skipping update."
            )
            return onboarding

        config = onboarding.config or {}
        config["vtex_host_store"] = resolved_url
        onboarding.config = config
        onboarding.save(update_fields=["config"])

        logger.info(
            f"[url_redirected] Updated store URL for onboarding={onboarding.uuid}: "
            f"original={original_url} -> resolved={resolved_url}"
        )

        self._send_vtex_host_store_to_connect(onboarding, resolved_url)
        return onboarding

    def _send_vtex_host_store_to_connect(
        self, onboarding: ProjectOnboarding, resolved_url: str
    ) -> None:
        """Propagates the resolved store URL to Connect. Non-blocking by design."""
        if onboarding.project is None:
            logger.warning(
                f"[url_redirected] Onboarding={onboarding.uuid} has no linked project. "
                f"Skipping Connect update."
            )
            return

        try:
            self.connect_service.update_project_config(
                project_uuid=str(onboarding.project.uuid),
                config={"vtex_host_store": resolved_url},
            )
        except Exception:
            logger.exception(
                f"[url_redirected] Failed to propagate vtex_host_store to Connect "
                f"for project={onboarding.project.uuid}"
            )

    @staticmethod
    def _handle_progress(
        onboarding: ProjectOnboarding, dto: CrawlerWebhookDTO
    ) -> ProjectOnboarding:
        """
        Logs a background-crawl progress event.

        Does NOT touch ``onboarding.progress`` -- the main wizard
        progress is owned by the inline orchestrator path (which has
        already moved on to ``NEXUS_CONFIG`` by the time these events
        arrive). The crawl phase reports its outcome via
        ``crawler_result``, not via ``progress``.
        """
        logger.info(
            f"Crawl background progress for onboarding={onboarding.uuid}: "
            f"event={dto.event} crawl_progress={dto.progress}%"
        )
        return onboarding
