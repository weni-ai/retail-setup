import logging

from celery import shared_task
from django.core.cache import cache

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.mark_onboarding_failed import mark_onboarding_failed
from retail.projects.usecases.onboarding_orchestrator import OnboardingOrchestrator
from retail.projects.usecases.start_crawl import CrawlerStartError, StartCrawlUseCase

logger = logging.getLogger(__name__)

WAIT_CRAWL_RETRY_COUNTDOWN = 10  # seconds between retries
WAIT_CRAWL_MAX_RETRIES = 60  # ~10 minutes of waiting
TASK_LOCK_TIMEOUT = 1800  # 30 min safety timeout


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


@shared_task(
    bind=True,
    name="task_wait_and_start_crawl",
    max_retries=WAIT_CRAWL_MAX_RETRIES,
)
def task_wait_and_start_crawl(self, vtex_account: str, crawl_url: str) -> None:
    """
    Waits for the project to be linked (via EDA), then triggers the crawl.

    Retries periodically until the project is available or max_retries is reached.
    """
    try:
        onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
    except ProjectOnboarding.DoesNotExist:
        mark_onboarding_failed(vtex_account, "Onboarding record not found")
        raise

    if onboarding.project is None:
        logger.info(
            f"Project not linked yet for vtex_account={vtex_account}. "
            f"Retrying in {WAIT_CRAWL_RETRY_COUNTDOWN}s..."
        )
        try:
            raise self.retry(countdown=WAIT_CRAWL_RETRY_COUNTDOWN)
        except self.MaxRetriesExceededError:
            mark_onboarding_failed(
                vtex_account,
                "Project was never linked: max retries exceeded",
            )
            raise

    logger.info(f"Project linked for vtex_account={vtex_account}. Starting crawl.")

    try:
        StartCrawlUseCase().execute(vtex_account, crawl_url)
    except CrawlerStartError as e:
        logger.error(f"Crawl start failed for vtex_account={vtex_account}: {e}")
        raise


@shared_task(name="task_configure_nexus")
def task_configure_nexus(vtex_account: str, contents: list) -> None:
    """
    Thin wrapper that delegates post-crawl configuration to the orchestrator.

    Ensures the task lock is released in all code paths.
    """
    try:
        OnboardingOrchestrator().execute(vtex_account, contents)
    finally:
        release_task_lock("configure_nexus", vtex_account)
