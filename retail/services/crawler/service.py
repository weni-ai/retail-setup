import logging

from typing import Dict, Optional

from retail.interfaces.clients.crawler.client import CrawlerClientInterface
from retail.clients.exceptions import CustomAPIException

logger = logging.getLogger(__name__)


class CrawlerService:
    """
    Service responsible for communicating with the Crawler microservice.
    Handles only the external request; business logic belongs in the usecase layer.
    """

    def __init__(self, crawler_client: CrawlerClientInterface):
        self.crawler_client = crawler_client

    def start_crawling(
        self, crawl_url: str, webhook_url: str, project_context: dict
    ) -> Optional[Dict]:
        """
        Triggers the crawler to start scraping a URL.

        Args:
            crawl_url: The URL the crawler will scrape to build the AI agent knowledge base.
            webhook_url: The callback URL for progress updates.
            project_context: Project metadata (vtex_account, objective, instructions).

        Returns:
            Dict with the crawler response (initial status), or None on failure.
        """
        try:
            return self.crawler_client.start_crawling(
                crawl_url, webhook_url, project_context
            )
        except CustomAPIException as e:
            logger.error(
                f"Error {e.status_code} starting crawl for crawl_url={crawl_url}: {e}"
            )
            return None
