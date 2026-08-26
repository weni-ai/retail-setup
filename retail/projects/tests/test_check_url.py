from unittest.mock import MagicMock

from django.test import TestCase

from retail.projects.usecases.check_url import CheckUrlResult, CheckUrlUseCase
from retail.projects.usecases.onboarding_dto import CheckUrlDTO


class TestCheckUrlUseCase(TestCase):
    def setUp(self):
        self.mock_crawler_service = MagicMock()
        self.usecase = CheckUrlUseCase(crawler_client=MagicMock())
        self.usecase.crawler_service = self.mock_crawler_service
        self.dto = CheckUrlDTO(
            vtex_account="mystore",
            crawl_url="https://www.mystore.com.br/",
        )

    def test_returns_valid_when_crawler_reports_reachable(self):
        self.mock_crawler_service.check_url.return_value = {
            "reachable": True,
            "resolved_url": "https://www.mystore.com.br/",
        }

        result = self.usecase.execute(self.dto)

        self.assertEqual(
            result,
            CheckUrlResult(valid=True, crawl_url="https://www.mystore.com.br/"),
        )
        self.mock_crawler_service.check_url.assert_called_once_with(
            "https://www.mystore.com.br/"
        )

    def test_uses_original_url_when_resolved_url_missing(self):
        self.mock_crawler_service.check_url.return_value = {"reachable": True}

        result = self.usecase.execute(self.dto)

        self.assertEqual(
            result,
            CheckUrlResult(valid=True, crawl_url="https://www.mystore.com.br/"),
        )

    def test_returns_invalid_when_crawler_reports_unreachable(self):
        self.mock_crawler_service.check_url.return_value = {
            "reachable": False,
            "resolved_url": "https://www.mystore.com.br/",
        }

        result = self.usecase.execute(self.dto)

        self.assertEqual(result, CheckUrlResult(valid=False))

    def test_returns_unavailable_when_crawler_comms_fail(self):
        self.mock_crawler_service.check_url.return_value = None

        result = self.usecase.execute(self.dto)

        self.assertEqual(result, CheckUrlResult(valid=False, unavailable=True))


class TestCheckUrlResult(TestCase):
    def test_to_dict_when_valid(self):
        result = CheckUrlResult(valid=True, crawl_url="https://www.mystore.com.br/")
        self.assertEqual(
            result.to_dict(),
            {"valid": True, "crawl_url": "https://www.mystore.com.br/"},
        )
        self.assertEqual(result.http_status, 200)

    def test_to_dict_when_unreachable(self):
        result = CheckUrlResult(valid=False)
        self.assertEqual(result.to_dict(), {"valid": False})
        self.assertEqual(result.http_status, 400)

    def test_to_dict_when_unavailable(self):
        result = CheckUrlResult(valid=False, unavailable=True)
        self.assertEqual(
            result.to_dict(),
            {"valid": False, "error": "unavailable"},
        )
        self.assertEqual(result.http_status, 502)
