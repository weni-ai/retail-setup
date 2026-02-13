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
    Uploads crawled content files to the Nexus content base.

    Progress: 0-80% of the NEXUS_CONFIG step.
    On success, dispatches task_configure_wwc to complete the step.
    """
    logger.info(f"Starting Nexus upload for vtex_account={vtex_account}")

    try:
        ConfigureAgentBuilderUseCase().execute(vtex_account, contents)
    except Exception as e:
        logger.error(f"Nexus upload failed for vtex_account={vtex_account}: {e}")
        raise
    finally:
        release_task_lock("configure_nexus", vtex_account)

    logger.info(
        f"Nexus upload completed for vtex_account={vtex_account}. "
        f"Dispatching WWC configuration."
    )
    task_configure_wwc.delay(vtex_account)


@shared_task(name="task_configure_wwc")
def task_configure_wwc(vtex_account: str) -> None:
    """
    Creates and configures the WWC (Weni Web Chat) channel.

    Progress: 90-100% of the NEXUS_CONFIG step.
    Only runs after Nexus uploads are complete.
    Protected against duplicates by the config.integrated_apps.wwc
    guard in ConfigureWWCUseCase.
    """
    logger.info(f"Starting WWC configuration for vtex_account={vtex_account}")

    try:
        ConfigureWWCUseCase().execute(vtex_account)
    except Exception as e:
        logger.error(f"WWC configuration failed for vtex_account={vtex_account}: {e}")
        raise

    logger.info(f"NEXUS_CONFIG completed for vtex_account={vtex_account}")
