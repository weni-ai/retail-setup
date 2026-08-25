from unittest.mock import MagicMock

from django.test import TestCase

from retail.clients.exceptions import CustomAPIException
from retail.services.crawler.service import CrawlerService


class TestCrawlerService(TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.service = CrawlerService(crawler_client=self.mock_client)
        self.crawl_url = "https://www.mystore.com.br/"
        self.webhook_url = "https://example.com/webhook"
        self.project_context = {
            "vtex_account": "mystore",
            "objective": "support",
            "instructions": [],
        }

    def test_start_crawling_success(self):
        expected = {"status": "started"}
        self.mock_client.start_crawling.return_value = expected

        result = self.service.start_crawling(
            self.crawl_url, self.webhook_url, self.project_context
        )

        self.mock_client.start_crawling.assert_called_once_with(
            self.crawl_url, self.webhook_url, self.project_context
        )
        self.assertEqual(result, expected)

    def test_start_crawling_returns_none_on_custom_api_exception(self):
        self.mock_client.start_crawling.side_effect = CustomAPIException(
            status_code=502, detail="crawler down"
        )

        result = self.service.start_crawling(
            self.crawl_url, self.webhook_url, self.project_context
        )

        self.assertIsNone(result)

    def test_detect_storefront_type_success(self):
        expected = {
            "store_url": self.crawl_url,
            "storefront_type": "vtex_io",
        }
        self.mock_client.detect_storefront_type.return_value = expected

        result = self.service.detect_storefront_type(self.crawl_url)

        self.mock_client.detect_storefront_type.assert_called_once_with(self.crawl_url)
        self.assertEqual(result, expected)

    def test_detect_storefront_type_returns_none_on_custom_api_exception(self):
        self.mock_client.detect_storefront_type.side_effect = CustomAPIException(
            status_code=500, detail="timeout"
        )

        result = self.service.detect_storefront_type(self.crawl_url)

        self.assertIsNone(result)

    def test_check_url_success(self):
        expected = {"reachable": True, "resolved_url": self.crawl_url}
        self.mock_client.check_url.return_value = expected

        result = self.service.check_url(self.crawl_url)

        self.mock_client.check_url.assert_called_once_with(self.crawl_url)
        self.assertEqual(result, expected)

    def test_check_url_returns_none_on_custom_api_exception(self):
        self.mock_client.check_url.side_effect = CustomAPIException(
            status_code=502, detail="crawler unavailable"
        )

        result = self.service.check_url(self.crawl_url)

        self.mock_client.check_url.assert_called_once_with(self.crawl_url)
        self.assertIsNone(result)
