import logging

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.tasks import task_setup_channel_and_start_crawl
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed
from retail.projects.usecases.onboarding_agents.agent_mappings import SUPPORTED_CHANNELS
from retail.projects.usecases.onboarding_access import (
    get_or_create_active_onboarding,
    onboarding_linked_to_active_project_record,
)
from retail.projects.usecases.onboarding_dto import StartSetupDTO

logger = logging.getLogger(__name__)


class StartSetupUseCase:
    """
    Initiates the setup process for a store.

    Creates/gets the onboarding record, stores channel configuration
    (including channel_data for wpp-cloud), then schedules a single
    background task that waits for the project link, creates the
    channel, and starts the crawl.

    The pre-crawl channel setup is dispatched unconditionally — even
    when the project is already linked — so the task owns the channel
    creation + crawl initiation pipeline end-to-end and the HTTP
    response returns immediately while the (potentially slow) Meta
    handshake runs asynchronously.
    """

    def execute(self, dto: StartSetupDTO) -> None:
        onboarding, created = get_or_create_active_onboarding(dto.vtex_account)

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
        channel_config = channels.setdefault(dto.channel, {})

        if dto.channel_data:
            channel_config["channel_data"] = dto.channel_data

        onboarding.config = config
        onboarding.current_step = "PROJECT_CONFIG"
        onboarding.progress = 0
        onboarding.save(update_fields=["config", "current_step", "progress"])

        try:
            self._try_link_project(onboarding)
        except Exception as exc:
            mark_onboarding_failed(dto.vtex_account, str(exc))
            raise

        task_setup_channel_and_start_crawl.delay(dto.vtex_account, dto.crawl_url)

        logger.info(
            f"Scheduled pre-crawl setup task for vtex_account={dto.vtex_account} "
            f"(project_linked={onboarding.project_id is not None}, "
            f"crawl_url={dto.crawl_url})"
        )

    @staticmethod
    def _reset_onboarding(onboarding: ProjectOnboarding) -> None:
        """
        Resets transient fields so a new pre-crawl cycle starts clean.

        Also clears any previously created channel ``app_uuid`` /
        ``flow_object_uuid`` so the new run can re-exchange a fresh
        ``auth_code`` without tripping the channel use case's
        idempotency guard.
        """
        onboarding.progress = 0
        onboarding.crawler_result = None
        onboarding.completed = False
        onboarding.failed = False
        onboarding.current_step = ""

        config = onboarding.config or {}
        config.pop("last_failure", None)
        config.pop("reason_failed", None)
        config.pop("background_error", None)
        config.pop("content_base_progress", None)

        channels = config.get("channels", {})
        for channel_config in channels.values():
            channel_config.pop("app_uuid", None)
            channel_config.pop("flow_object_uuid", None)

        onboarding.config = config

        onboarding.save(
            update_fields=[
                "progress",
                "crawler_result",
                "completed",
                "failed",
                "current_step",
                "config",
            ]
        )

    @staticmethod
    def _try_link_project(onboarding: ProjectOnboarding) -> None:
        """
        Skips when project_id already points to an active Project. A stale
        FK to a soft-deleted project is replaced by the active match.
        """
        if onboarding_linked_to_active_project_record(onboarding):
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
