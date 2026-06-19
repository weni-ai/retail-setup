"""
End-to-end test for the full onboarding flow.

Simulates every step, from start-setup to agent integration,
with all external services mocked.
"""

from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
    MANAGER_DONE_PROGRESS,
)
from retail.projects.usecases.configure_wwc import (
    PROJECT_CONFIG_AFTER_PERSIST,
    ConfigureWWCUseCase,
)
from retail.projects.usecases.integrate_agents import IntegrateAgentsUseCase
from retail.projects.usecases.link_project_to_onboarding import (
    PROJECT_LINKED_PROGRESS,
    LinkProjectToOnboardingUseCase,
)
from retail.projects.usecases.onboarding_dto import (
    CrawlerWebhookDTO,
    StartSetupDTO,
)
from retail.projects.usecases.onboarding_orchestrator import OnboardingOrchestrator
from retail.projects.usecases.start_crawl import (
    CRAWL_KICKOFF_PROGRESS,
    StartCrawlUseCase,
)
from retail.projects.usecases.start_setup import StartSetupUseCase
from retail.projects.usecases.update_onboarding_progress import (
    UpdateOnboardingProgressUseCase,
)
from retail.projects.usecases.upload_nexus_contents import (
    UploadNexusContentsUseCase,
)


class TestFullOnboardingFlow(TestCase):
    """
    Simulates the full onboarding flow end-to-end (post background-crawl
    refactor):

    Main (inline) path -- single Celery task:
      1. Front-end calls start-setup (project not linked yet) -> PROJECT_CONFIG 0%
      2. EDA links the project                                -> PROJECT_CONFIG 30%
      3. Pre-crawl channel setup runs                         -> PROJECT_CONFIG 100%
      4. Crawl kicked off (fire-and-forget)                   -> CRAWL 100%
      5. Orchestrator: agent manager configured               -> NEXUS_CONFIG 10 -> 75
      6. Orchestrator: agent integration                      -> NEXUS_CONFIG 100

    Background path (decoupled from the wizard):
      7. Crawler sends progress events                        -> NO main progress change
      8. Crawler sends crawl.completed                        -> crawler_result=SUCCESS,
                                                                 task_upload_nexus_contents
                                                                 dispatched
      9. task_upload_nexus_contents uploads contents to Nexus -> NO main progress change
    """

    def setUp(self):
        self.vtex_account = "flowstore"
        self.project_uuid = uuid4()
        self.crawl_url = "https://www.flowstore.com.br/"
        self.channel_app_uuid = str(uuid4())

    @patch("retail.projects.usecases.start_setup.task_setup_channel_and_start_crawl")
    def test_full_flow(self, mock_setup_task):
        # -- Step 1: Front-end starts setup, no project yet --
        dto = StartSetupDTO(
            vtex_account=self.vtex_account,
            crawl_url=self.crawl_url,
            channel="wwc",
        )
        StartSetupUseCase().execute(dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account=self.vtex_account)
        self.assertIsNone(onboarding.project)
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, 0)
        self.assertIn("wwc", onboarding.config["channels"])
        mock_setup_task.delay.assert_called_once_with(self.vtex_account, self.crawl_url)

        # -- Step 2: EDA links the project (partial PROJECT_CONFIG progress) --
        project = Project.objects.create(
            name="Flow Store",
            uuid=self.project_uuid,
            vtex_account=self.vtex_account,
        )
        LinkProjectToOnboardingUseCase.execute(project)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.project, project)
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, PROJECT_LINKED_PROGRESS)

        # -- Step 3: Pre-crawl channel setup completes PROJECT_CONFIG --
        mock_integrations_service = MagicMock()
        mock_integrations_service.create_channel_app.return_value = {
            "uuid": self.channel_app_uuid,
            "code": "wwc",
        }
        mock_integrations_service.configure_channel_app.return_value = {
            "uuid": self.channel_app_uuid,
            "script": "https://example.com/script.js",
        }

        wwc_usecase = ConfigureWWCUseCase(integrations_client=MagicMock())
        wwc_usecase.integrations_service = mock_integrations_service
        wwc_usecase.execute(self.vtex_account)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, PROJECT_CONFIG_AFTER_PERSIST)
        self.assertEqual(
            onboarding.config["channels"]["wwc"]["app_uuid"],
            self.channel_app_uuid,
        )

        # -- Step 4: Crawl kicked off (background, CRAWL 100%) --
        mock_crawler_service = MagicMock()
        mock_crawler_service.start_crawling.return_value = {"status": "started"}

        crawl_usecase = StartCrawlUseCase(crawler_client=MagicMock())
        crawl_usecase.crawler_service = mock_crawler_service
        crawl_usecase.execute(self.vtex_account, self.crawl_url)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.current_step, "CRAWL")
        self.assertEqual(onboarding.progress, CRAWL_KICKOFF_PROGRESS)

        # -- Steps 5 + 6: Inline orchestrator runs the post-crawl steps --
        mock_nexus_service = MagicMock()
        mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        mock_nexus_service_agents = MagicMock()
        mock_nexus_service_agents.integrate_agent.return_value = {"ok": True}

        with patch(
            "retail.projects.usecases.onboarding_orchestrator.ConfigureAgentBuilderUseCase"
        ) as mock_agent_cls, patch(
            "retail.projects.usecases.onboarding_orchestrator.IntegrateAgentsUseCase"
        ) as mock_integrate_cls:
            agent_usecase = ConfigureAgentBuilderUseCase(nexus_client=MagicMock())
            agent_usecase.nexus_service = mock_nexus_service
            mock_agent_cls.return_value = agent_usecase

            integrate_usecase = IntegrateAgentsUseCase(nexus_client=MagicMock())
            integrate_usecase.nexus_service = mock_nexus_service_agents
            mock_integrate_cls.return_value = integrate_usecase

            with patch(
                "retail.projects.usecases.integrate_agents.get_channel_agents",
                return_value=[],
            ):
                OnboardingOrchestrator().execute(self.vtex_account)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.current_step, "NEXUS_CONFIG")
        self.assertEqual(onboarding.progress, 100)
        mock_nexus_service.configure_agent_attributes.assert_called_once()
        mock_nexus_service.upload_content_base_file.assert_not_called()

        # The wizard is effectively done here; main onboarding is complete
        # from the user's perspective. The background phase below MUST
        # NOT regress current_step or progress.

        # -- Step 7: Crawler sends progress (background, ignored by main) --
        progress_dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url=self.crawl_url,
            progress=50,
        )
        result = UpdateOnboardingProgressUseCase().execute(
            str(onboarding.uuid), progress_dto
        )
        self.assertEqual(result.current_step, "NEXUS_CONFIG")
        self.assertEqual(result.progress, 100)

        # -- Step 8: Crawler sends crawl.completed (background) --
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
            "retail.projects.usecases.update_onboarding_progress.task_upload_nexus_contents"
        ) as mock_nexus_task:
            completed_dto = CrawlerWebhookDTO(
                task_id="task-1",
                event="crawl.completed",
                timestamp="2026-01-01T01:00:00Z",
                url=self.crawl_url,
                progress=100,
                data={"contents": crawled_contents},
            )
            result = UpdateOnboardingProgressUseCase().execute(
                str(onboarding.uuid), completed_dto
            )

        self.assertEqual(result.current_step, "NEXUS_CONFIG")
        self.assertEqual(result.progress, 100)
        self.assertEqual(result.crawler_result, ProjectOnboarding.SUCCESS)
        mock_nexus_task.delay.assert_called_once_with(
            self.vtex_account, crawled_contents
        )

        # -- Step 9: Background upload runs -- NO main progress change --
        background_nexus = MagicMock()
        background_nexus.check_agent_builder_exists.return_value = {
            "data": {"has_agent": True}
        }
        background_nexus.upload_content_base_file.return_value = {
            "uuid": str(uuid4()),
            "extension_file": "txt",
        }
        background_nexus.get_content_base_file_status.return_value = {
            "status": "success",
        }

        background_usecase = UploadNexusContentsUseCase(nexus_client=MagicMock())
        background_usecase.nexus_service = background_nexus

        with patch("retail.projects.usecases.upload_nexus_contents.time.sleep"):
            background_usecase.execute(self.vtex_account, crawled_contents)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.current_step, "NEXUS_CONFIG")
        self.assertEqual(onboarding.progress, 100)
        self.assertEqual(background_nexus.upload_content_base_file.call_count, 2)

        # -- Final state check --
        self.assertFalse(onboarding.completed)
        self.assertFalse(onboarding.failed)
        self.assertEqual(onboarding.crawler_result, ProjectOnboarding.SUCCESS)
        # Sanity: the manager-done milestone fires inside the orchestrator
        self.assertGreaterEqual(MANAGER_DONE_PROGRESS, 1)
