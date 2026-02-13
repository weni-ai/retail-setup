"""
End-to-end test for the full onboarding flow.

Simulates every step, from start-crawling to WWC channel creation,
with all external services mocked.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
)
from retail.projects.usecases.configure_wwc import ConfigureWWCUseCase
from retail.projects.usecases.link_project_to_onboarding import (
    LinkProjectToOnboardingUseCase,
)
from retail.projects.usecases.onboarding_dto import (
    CrawlerWebhookDTO,
    StartOnboardingDTO,
)
from retail.projects.usecases.start_crawl import StartCrawlUseCase
from retail.projects.usecases.start_onboarding import StartOnboardingUseCase
from retail.projects.usecases.update_onboarding_progress import (
    UpdateOnboardingProgressUseCase,
)


class TestFullOnboardingFlow(TestCase):
    """
    Simulates the full onboarding flow end-to-end:

    1. Front-end calls start-crawling (project not linked yet)
    2. EDA links the project → PROJECT_CONFIG 100%
    3. Crawler sends progress events
    4. Crawler sends crawl.completed
    5. Nexus upload is executed
    6. WWC channel is created and configured
    """

    def setUp(self):
        self.vtex_account = "flowstore"
        self.project_uuid = uuid4()
        self.crawl_url = "https://www.flowstore.com.br/"
        self.wwc_app_uuid = str(uuid4())

    @patch("retail.projects.usecases.start_onboarding.task_wait_and_start_crawl")
    def test_full_flow(self, mock_wait_task):
        # ── Step 1: Front-end starts crawling, no project yet ──
        dto = StartOnboardingDTO(
            vtex_account=self.vtex_account,
            crawl_url=self.crawl_url,
        )
        StartOnboardingUseCase().execute(dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account=self.vtex_account)
        self.assertIsNone(onboarding.project)
        self.assertEqual(onboarding.progress, 0)
        mock_wait_task.delay.assert_called_once_with(self.vtex_account, self.crawl_url)

        # ── Step 2: EDA links the project ──
        project = Project.objects.create(
            name="Flow Store",
            uuid=self.project_uuid,
            vtex_account=self.vtex_account,
        )
        LinkProjectToOnboardingUseCase.execute(project)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.project, project)
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, 100)

        # ── Step 3: Simulate the wait task starting the crawl ──
        mock_crawler_service = MagicMock()
        mock_crawler_service.start_crawling.return_value = {"status": "started"}

        crawl_usecase = StartCrawlUseCase(crawler_client=MagicMock())
        crawl_usecase.crawler_service = mock_crawler_service
        crawl_usecase.execute(self.vtex_account, self.crawl_url)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.current_step, "CRAWL")
        self.assertEqual(onboarding.progress, 0)

        # ── Step 4: Crawler sends progress update ──
        progress_dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url=self.crawl_url,
            progress=50,
        )
        result = UpdateOnboardingProgressUseCase.execute(
            str(self.project_uuid), progress_dto
        )
        self.assertEqual(result.progress, 50)

        # ── Step 5: Crawler sends crawl.completed ──
        crawled_contents = [
            {
                "link": "https://www.flowstore.com.br/",
                "title": "Home",
                "content": "Welcome to Flow Store",
            },
            {
                "link": "https://www.flowstore.com.br/about",
                "title": "About",
                "content": "We sell amazing products",
            },
        ]

        with patch(
            "retail.projects.usecases.update_onboarding_progress.acquire_task_lock",
            return_value=True,
        ), patch(
            "retail.projects.usecases.update_onboarding_progress.task_configure_nexus"
        ) as mock_nexus_task:
            completed_dto = CrawlerWebhookDTO(
                task_id="task-1",
                event="crawl.completed",
                timestamp="2026-01-01T01:00:00Z",
                url=self.crawl_url,
                progress=100,
                data={"contents": crawled_contents},
            )
            result = UpdateOnboardingProgressUseCase.execute(
                str(self.project_uuid), completed_dto
            )

        self.assertEqual(result.progress, 100)
        self.assertEqual(result.crawler_result, ProjectOnboarding.SUCCESS)
        mock_nexus_task.delay.assert_called_once_with(
            self.vtex_account, crawled_contents
        )

        # ── Step 6: Nexus upload (simulated synchronously) ──
        mock_nexus_service = MagicMock()
        mock_nexus_service.upload_content_base_file.return_value = {"status": "ok"}

        agent_usecase = ConfigureAgentBuilderUseCase(nexus_client=MagicMock())
        agent_usecase.nexus_service = mock_nexus_service
        agent_usecase.execute(self.vtex_account, crawled_contents)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.current_step, "NEXUS_CONFIG")
        self.assertEqual(onboarding.progress, 80)  # MAX_UPLOAD_PROGRESS
        self.assertEqual(mock_nexus_service.upload_content_base_file.call_count, 2)

        # ── Step 7: WWC channel creation and configuration ──
        mock_integrations_service = MagicMock()
        mock_integrations_service.create_wwc_app.return_value = {
            "uuid": self.wwc_app_uuid,
            "code": "wwc",
        }
        mock_integrations_service.configure_wwc_app.return_value = {
            "uuid": self.wwc_app_uuid,
            "script": "https://example.com/script.js",
        }

        wwc_usecase = ConfigureWWCUseCase(integrations_client=MagicMock())
        wwc_usecase.integrations_service = mock_integrations_service
        wwc_usecase.execute(self.vtex_account)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.progress, 100)
        self.assertEqual(onboarding.current_step, "NEXUS_CONFIG")
        self.assertEqual(
            onboarding.config["integrated_apps"]["wwc"],
            self.wwc_app_uuid,
        )

        # ── Final state check ──
        self.assertFalse(onboarding.completed)  # Only front-end sets this
        self.assertEqual(onboarding.crawler_result, ProjectOnboarding.SUCCESS)
