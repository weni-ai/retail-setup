import logging
from dataclasses import dataclass
from typing import Optional

from retail.clients.crawler.client import CrawlerClient
from retail.interfaces.clients.crawler.client import CrawlerClientInterface
from retail.projects.usecases.onboarding_dto import CheckUrlDTO
from retail.services.crawler.service import CrawlerService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckUrlResult:
    """Outcome of a crawl-URL reachability check."""

    valid: bool
    crawl_url: Optional[str] = None
    unavailable: bool = False

    def to_dict(self) -> dict:
        if self.unavailable:
            return {"valid": False, "error": "unavailable"}
        if self.valid:
            return {"valid": True, "crawl_url": self.crawl_url}
        return {"valid": False}

    @property
    def http_status(self) -> int:
        return 502 if self.unavailable else 200


class CheckUrlUseCase:
    """
    Proxies a reachability check to the Crawler MS.

    Distinguishes crawler-comms failure (``unavailable``) from a reachable
    check that returned ``reachable: false``, so the front-end can show
    different copy.
    """

    def __init__(self, crawler_client: CrawlerClientInterface = None):
        self.crawler_service = CrawlerService(
            crawler_client=crawler_client or CrawlerClient()
        )

    def execute(self, dto: CheckUrlDTO) -> CheckUrlResult:
        logger.info(
            f"Checking crawl url for vtex_account={dto.vtex_account} "
            f"crawl_url={dto.crawl_url}"
        )

        response = self.crawler_service.check_url(dto.crawl_url)

        if response is None:
            logger.error(
                f"Crawler check-url unavailable for "
                f"vtex_account={dto.vtex_account} crawl_url={dto.crawl_url}"
            )
            return CheckUrlResult(valid=False, unavailable=True)

        if response.get("reachable"):
            resolved = response.get("resolved_url") or dto.crawl_url
            logger.info(
                f"Crawl url reachable for vtex_account={dto.vtex_account} "
                f"resolved_url={resolved}"
            )
            return CheckUrlResult(valid=True, crawl_url=resolved)

        logger.info(
            f"Crawl url unreachable for vtex_account={dto.vtex_account} "
            f"crawl_url={dto.crawl_url}"
        )
        return CheckUrlResult(valid=False)
