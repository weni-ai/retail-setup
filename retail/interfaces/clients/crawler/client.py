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
