from typing import Dict, Protocol


class CrawlerClientInterface(Protocol):
    """
    Interface for Crawler MS client operations.
    """

    def start_crawling(
        self, crawl_url: str, webhook_url: str, project_context: dict
    ) -> Dict:
        """
        Starts the crawling process for a given URL.

        Args:
            crawl_url: The URL the crawler will scrape to build the AI agent knowledge base.
            webhook_url: The URL the crawler will ping with progress updates.
            project_context: Project metadata (vtex_account, objective, instructions).

        Returns:
            Dict: Response data from the crawler service (initial status).
        """
        ...

    def detect_storefront_type(self, store_url: str) -> Dict:
        """
        Detects the storefront technology used by a VTEX store.

        Args:
            store_url: The store URL to inspect (must start with http:// or https://).

        Returns:
            Dict with ``store_url`` and ``storefront_type``
            (one of: faststore, vtex_io, legacy, unknown).
        """
        ...
