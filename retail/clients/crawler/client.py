"""Client for communication with the Crawler microservice (internal DNS, no auth)."""

import logging

from typing import Dict

from django.conf import settings

from retail.clients.base import RequestClient
from retail.interfaces.clients.crawler.client import CrawlerClientInterface

logger = logging.getLogger(__name__)


class CrawlerClient(RequestClient, CrawlerClientInterface):
    def __init__(self):
        self.base_url = settings.CRAWLER_REST_ENDPOINT

    def start_crawling(
        self, crawl_url: str, webhook_url: str, project_context: dict
    ) -> Dict:
        """
        Starts the crawling process for a given URL.

        No authentication is required — the crawler is accessible
        only via internal DNS and is not publicly exposed.

        Args:
            crawl_url: The URL the crawler will scrape to build the AI agent knowledge base.
            webhook_url: The URL the crawler will ping with progress updates.
            project_context: Project metadata (vtex_account, objective, instructions).

        Returns:
            Dict: Response data from the crawler service (initial status).
        """
        url = f"{self.base_url}/api/crawl"
        payload = {
            "crawl_url": crawl_url,
            "webhook_url": webhook_url,
            "project": project_context,
        }

        response = self.make_request(
            url,
            method="POST",
            json=payload,
        )
        return response.json()

    def detect_storefront_type(self, store_url: str) -> Dict:
        """
        Detects which VTEX storefront platform a store is running.

        Args:
            store_url: The store URL to inspect (must start with http:// or https://).

        Returns:
            Dict with ``store_url`` and ``storefront_type``.
        """
        url = f"{self.base_url}/api/storefront-type"
        response = self.make_request(
            url,
            method="GET",
            params={"store_url": store_url},
        )
        return response.json()
