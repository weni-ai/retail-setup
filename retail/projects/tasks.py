import logging

from celery import shared_task
from django.core.cache import cache

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
)
from retail.projects.usecases.configure_wwc import ConfigureWWCUseCase
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
    onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)

    if onboarding.project is None:
        logger.info(
            f"Project not linked yet for vtex_account={vtex_account}. "
            f"Retrying in {WAIT_CRAWL_RETRY_COUNTDOWN}s..."
        )
        raise self.retry(countdown=WAIT_CRAWL_RETRY_COUNTDOWN)

    logger.info(f"Project linked for vtex_account={vtex_account}. Starting crawl.")

    try:
        StartCrawlUseCase().execute(vtex_account, crawl_url)
    except CrawlerStartError as e:
        logger.error(f"Crawl start failed for vtex_account={vtex_account}: {e}")
        raise


@shared_task(name="task_configure_nexus")
def task_configure_nexus(vtex_account: str, contents: list) -> None:
    """
    Orchestrates post-crawl configuration:
      1. WWC channel creation (synchronous, 0-10%)
      2. Nexus manager config + content upload (10-100%)

    WWC runs first because it's fast and synchronous, providing
    immediate feedback to the front-end. Nexus uploads are heavier
    and run last so progress grows gradually.
    """
    logger.info(f"Starting post-crawl config for vtex_account={vtex_account}")

    try:
        ConfigureWWCUseCase().execute(vtex_account)
    except Exception as e:
        logger.error(f"WWC configuration failed for vtex_account={vtex_account}: {e}")
        raise

    try:
        ConfigureAgentBuilderUseCase().execute(vtex_account, contents)
    except Exception as e:
        logger.error(f"Nexus config failed for vtex_account={vtex_account}: {e}")
        raise
    finally:
        release_task_lock("configure_nexus", vtex_account)

    logger.info(f"NEXUS_CONFIG completed for vtex_account={vtex_account}")
