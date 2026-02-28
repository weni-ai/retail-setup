from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase, override_settings

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.manager_defaults import MANAGER_DEFAULTS
from retail.projects.usecases.start_crawl import (
    CrawlerStartError,
    StartCrawlUseCase,
)


@override_settings(DOMAIN="https://retail.weni.ai")
class TestStartCrawlUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
            language="pt-br",
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
        )
        self.mock_crawler_service = MagicMock()
        self.usecase = StartCrawlUseCase(crawler_client=MagicMock())
        self.usecase.crawler_service = self.mock_crawler_service

    def test_sets_step_to_crawl_and_progress_to_zero(self):
        self.mock_crawler_service.start_crawling.return_value = {"status": "started"}

        self.usecase.execute("mystore", "https://www.mystore.com.br/")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_step, "CRAWL")
        self.assertEqual(self.onboarding.progress, 0)

    def test_calls_crawler_service_with_correct_args(self):
        self.mock_crawler_service.start_crawling.return_value = {"status": "started"}

        self.usecase.execute("mystore", "https://www.mystore.com.br/")

        self.mock_crawler_service.start_crawling.assert_called_once()
        args = self.mock_crawler_service.start_crawling.call_args
        self.assertEqual(args[0][0], "https://www.mystore.com.br/")
        self.assertIn(str(self.onboarding.uuid), args[0][1])  # webhook_url
        self.assertEqual(args[0][2]["account_name"], "mystore")

    def test_raises_error_when_crawler_fails(self):
        self.mock_crawler_service.start_crawling.return_value = None

        with self.assertRaises(CrawlerStartError):
            self.usecase.execute("mystore", "https://www.mystore.com.br/")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.crawler_result, ProjectOnboarding.FAIL)

    def test_build_webhook_url(self):
        onboarding_uuid = str(uuid4())
        url = StartCrawlUseCase._build_webhook_url(onboarding_uuid)

        self.assertEqual(
            url,
            f"https://retail.weni.ai/api/onboard/{onboarding_uuid}/webhook/",
        )

    def test_build_project_context_with_pt(self):
        context = StartCrawlUseCase._build_project_context("mystore", "pt-br")

        self.assertEqual(context["account_name"], "mystore")
        self.assertEqual(context["objective"], MANAGER_DEFAULTS["pt"]["goal"])
        self.assertIn("instructions", context)

    def test_build_project_context_with_en(self):
        context = StartCrawlUseCase._build_project_context("mystore", "en-us")

        self.assertEqual(context["objective"], MANAGER_DEFAULTS["en"]["goal"])

    def test_raises_does_not_exist_for_unknown_vtex_account(self):
        with self.assertRaises(ProjectOnboarding.DoesNotExist):
            self.usecase.execute("unknown", "https://unknown.com/")
