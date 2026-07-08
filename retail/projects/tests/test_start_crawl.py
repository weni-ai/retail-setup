from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase, override_settings

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.manager_defaults import MANAGER_DEFAULTS
from retail.projects.usecases.start_crawl import StartCrawlUseCase


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
            current_step="NEXUS_CONFIG",
            progress=0,
        )
        self.mock_crawler_service = MagicMock()
        self.usecase = StartCrawlUseCase(crawler_client=MagicMock())
        self.usecase.crawler_service = self.mock_crawler_service

    def test_does_not_change_step_or_progress(self):
        """Step/progress transitions are owned by OnboardingOrchestrator."""
        self.mock_crawler_service.start_crawling.return_value = {"status": "started"}

        self.usecase.execute("mystore", "https://www.mystore.com.br/")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_step, "NEXUS_CONFIG")
        self.assertEqual(self.onboarding.progress, 0)

    def test_calls_crawler_service_with_correct_args(self):
        self.mock_crawler_service.start_crawling.return_value = {"status": "started"}

        self.usecase.execute("mystore", "https://www.mystore.com.br/")

        self.mock_crawler_service.start_crawling.assert_called_once()
        args = self.mock_crawler_service.start_crawling.call_args
        self.assertEqual(args[0][0], "https://www.mystore.com.br/")
        self.assertIn(str(self.onboarding.uuid), args[0][1])  # webhook_url
        self.assertEqual(args[0][2]["account_name"], "mystore")

    @patch("retail.projects.usecases.start_crawl.SaveBackgroundFailureUseCase")
    def test_soft_fails_when_crawler_unreachable(self, mock_save_background_cls):
        """
        On crawler-comms failure the use case must NOT raise (so the
        inline orchestrator can still complete the wizard) but must record
        a soft failure under ``config["background_error"]`` and set
        ``crawler_result=FAIL``.
        """
        self.mock_crawler_service.start_crawling.return_value = None

        self.usecase.execute("mystore", "https://www.mystore.com.br/")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.crawler_result, ProjectOnboarding.FAIL)
        self.assertFalse(self.onboarding.failed)

        mock_save_background_cls.execute.assert_called_once()
        called_args = mock_save_background_cls.execute.call_args[0]
        self.assertEqual(called_args[0], "mystore")
        self.assertEqual(called_args[1], "crawler_start")

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
