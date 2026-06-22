import logging

from celery import shared_task
from django.core.cache import cache

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed
from retail.projects.usecases.onboarding_orchestrator import OnboardingOrchestrator
from retail.projects.usecases.pre_crawl_channel import PreCrawlChannelUseCase
from retail.projects.usecases.save_background_failure import (
    SaveBackgroundFailureUseCase,
)
from retail.projects.usecases.upload_nexus_contents import UploadNexusContentsUseCase
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)

WAIT_CRAWL_RETRY_COUNTDOWN = 10  # seconds between retries
WAIT_CRAWL_MAX_RETRIES = 60  # ~10 minutes of waiting
TASK_LOCK_TIMEOUT = 1800  # 30 min safety timeout

# Progress marker set right before invoking the channel use case so the
# frontend reflects "project linked, starting channel setup" regardless of
# whether the project was linked inline (StartSetupUseCase) or async (EDA).
PROJECT_LINKED_PROGRESS = 30


def _lock_key(task_name: str, vtex_account: str) -> str:
    return f"task_lock:{task_name}:{vtex_account}"


def acquire_task_lock(task_name: str, vtex_account: str) -> bool:
    """
    Atomically acquires a task lock for the given vtex_account.

    Returns True if acquired, False if already held by another execution.
    """
    return cache.add(
        _lock_key(task_name, vtex_account), True, timeout=TASK_LOCK_TIMEOUT
    )


def release_task_lock(task_name: str, vtex_account: str) -> None:
    """Releases a previously acquired task lock."""
    cache.delete(_lock_key(task_name, vtex_account))


def _run_setup_channel_and_start_crawl(task, vtex_account: str, crawl_url: str) -> None:
    """
    Shared implementation for the pre-crawl + post-crawl pipeline.

    Both ``task_setup_channel_and_start_crawl`` (new name) and the
    legacy alias ``task_wait_and_start_crawl`` delegate here so the
    same retry/cleanup logic runs regardless of how the task was
    enqueued.

    Pipeline order (single Celery task, sequential):
      1. Wait until the project is linked (retries up to ~10 minutes).
      2. Pre-crawl channel setup (WWC or WPP Cloud).
      3. Run the NEXUS_CONFIG orchestrator inline (crawl kickoff +
         manager + payment + agents -- no content upload). The wizard
         completes here; the content upload happens in background later
         when the crawler webhook arrives.

    Args:
        task: The bound Celery task instance (provides ``retry`` /
            ``MaxRetriesExceededError``).
        vtex_account: VTEX account identifier.
        crawl_url: Store URL to crawl after channel setup.
    """
    try:
        onboarding = ProjectOnboarding.objects.select_related("project").get(
            vtex_account=vtex_account,
        )
    except ProjectOnboarding.DoesNotExist:
        mark_onboarding_failed(vtex_account, "Onboarding record not found")
        raise

    if onboarding.project is None:
        logger.info(
            f"Project not linked yet for vtex_account={vtex_account}. "
            f"Retrying in {WAIT_CRAWL_RETRY_COUNTDOWN}s..."
        )
        try:
            raise task.retry(countdown=WAIT_CRAWL_RETRY_COUNTDOWN)
        except task.MaxRetriesExceededError:
            mark_onboarding_failed(
                vtex_account,
                "Project was never linked: max retries exceeded",
            )
            raise

    logger.info(
        f"Project linked for vtex_account={vtex_account}. "
        f"Running pre-crawl channel setup."
    )

    if (
        onboarding.current_step != "PROJECT_CONFIG"
        or onboarding.progress < PROJECT_LINKED_PROGRESS
    ):
        onboarding.current_step = "PROJECT_CONFIG"
        onboarding.progress = PROJECT_LINKED_PROGRESS
        onboarding.save(update_fields=["current_step", "progress"])

    try:
        PreCrawlChannelUseCase().execute(vtex_account)
    except Exception as exc:
        mark_onboarding_failed(vtex_account, f"Channel creation failed: {exc}")
        raise

    OnboardingOrchestrator().execute(vtex_account, crawl_url)


@shared_task(
    bind=True,
    name="task_setup_channel_and_start_crawl",
    max_retries=WAIT_CRAWL_MAX_RETRIES,
)
def task_setup_channel_and_start_crawl(self, vtex_account: str, crawl_url: str) -> None:
    """
    Pre-crawl + NEXUS_CONFIG orchestration: wait for project link, create
    channel, then run the NEXUS_CONFIG orchestrator inline (crawl kickoff +
    manager + payment + agents) so the wizard completes without waiting
    for the crawl.

    The Facebook ``auth_code`` from Embedded Signup is short-lived, so the
    channel must be created (and the code exchanged on the
    integrations-engine side) before the long-running crawl can expire it.

    Retries while the project is not linked. Once linked, runs the channel
    use case (resolves wwc or wpp-cloud) and the orchestrator. If channel
    creation fails, the onboarding is marked failed and the orchestrator is
    not invoked -- the user must redo Embedded Signup.
    """
    return _run_setup_channel_and_start_crawl(self, vtex_account, crawl_url)


@shared_task(
    bind=True,
    name="task_wait_and_start_crawl",
    max_retries=WAIT_CRAWL_MAX_RETRIES,
)
def task_wait_and_start_crawl(self, vtex_account: str, crawl_url: str) -> None:
    """
    Deprecated alias for ``task_setup_channel_and_start_crawl``.

    Kept registered under the original Celery task name so in-flight
    retries queued before the rename keep executing the new pre-crawl
    pipeline. New dispatches use the renamed task directly.
    """
    return _run_setup_channel_and_start_crawl(self, vtex_account, crawl_url)


@shared_task(name="task_activate_agentic_cx_script")
def task_activate_agentic_cx_script(vtex_account: str) -> None:
    """
    Notifies the VTEX IO app that the onboarding is complete
    and the Agentic CX script can be installed on the storefront.
    """
    account_domain = f"{vtex_account}.myvtex.com"
    VtexIOService().activate_agentic_cx_script(
        account_domain=account_domain,
        vtex_account=vtex_account,
    )
    logger.info(f"Agentic CX script activated for vtex_account={vtex_account}")


UPLOAD_NEXUS_LOCK_NAME = "upload_nexus_contents"


def _run_upload_nexus_contents(vtex_account: str, contents: list) -> None:
    """
    Shared implementation for the background Nexus content upload.

    Both ``task_upload_nexus_contents`` (new canonical name) and the
    deprecated alias ``task_configure_nexus`` delegate here so the same
    soft-failure + lock-release semantics run regardless of which task
    name was used to enqueue the job.

    Soft-fails on any exception: the post-crawl orchestrator (manager +
    payment + agents) has already run inline as part of
    ``task_setup_channel_and_start_crawl`` and the wizard may already
    be complete from the user's perspective -- so a failure here lands
    in ``config["background_error"]`` and does NOT flip
    ``onboarding.failed``.
    """
    try:
        UploadNexusContentsUseCase().execute(vtex_account, contents)
    except Exception as exc:
        logger.exception(
            f"Background nexus upload failed for vtex_account={vtex_account}"
        )
        SaveBackgroundFailureUseCase.execute(vtex_account, "nexus_upload", str(exc))
    finally:
        release_task_lock(UPLOAD_NEXUS_LOCK_NAME, vtex_account)


@shared_task(name="task_upload_nexus_contents")
def task_upload_nexus_contents(vtex_account: str, contents: list) -> None:
    """
    Background-only: uploads crawled contents to Nexus.

    Dispatched by ``UpdateOnboardingProgressUseCase`` when the
    ``crawl.completed`` webhook arrives.
    """
    return _run_upload_nexus_contents(vtex_account, contents)


@shared_task(name="task_configure_nexus")
def task_configure_nexus(vtex_account: str, contents: list) -> None:
    """
    Deprecated alias for ``task_upload_nexus_contents``.

    Kept registered under the original Celery task name so any jobs
    queued before the rename keep executing the new upload pipeline.
    All new dispatches MUST use ``task_upload_nexus_contents`` directly;
    this alias can be removed once no more in-flight ``task_configure_nexus``
    messages exist in the broker.
    """
    return _run_upload_nexus_contents(vtex_account, contents)
