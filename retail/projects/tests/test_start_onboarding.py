from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_dto import StartSetupDTO
from retail.projects.usecases.start_setup import StartSetupUseCase


class TestStartSetupUseCase(TestCase):
    def setUp(self):
        self.dto = StartSetupDTO(
            vtex_account="mystore",
            crawl_url="https://www.mystore.com.br/",
            channel="wwc",
        )

    @patch("retail.projects.usecases.start_setup.task_wait_and_start_crawl")
    def test_creates_onboarding_and_schedules_wait_task_when_no_project(
        self, mock_task
    ):
        """When no project exists, should schedule task_wait_and_start_crawl."""
        usecase = StartSetupUseCase()

        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertIsNone(onboarding.project)
        mock_task.delay.assert_called_once_with(
            "mystore", "https://www.mystore.com.br/"
        )

    def test_initiates_crawl_immediately_when_project_exists(self):
        """When a project is linked, should call InitiateCrawlUseCase."""
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

        mock_initiate_crawl = MagicMock()
        usecase = StartSetupUseCase(initiate_crawl_usecase=mock_initiate_crawl)

        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertEqual(onboarding.project, project)
        mock_initiate_crawl.execute.assert_called_once_with(
            project, "mystore", "https://www.mystore.com.br/"
        )

    @patch("retail.projects.usecases.start_setup.task_wait_and_start_crawl")
    @patch("retail.projects.tasks.task_activate_agentic_cx_script")
    def test_resets_existing_onboarding_on_retry(self, _mock_agentic, mock_task):
        """When an onboarding already exists, should reset transient fields."""
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            current_step="CRAWL",
            progress=80,
            crawler_result=ProjectOnboarding.SUCCESS,
            completed=True,
            config={
                "last_failure": {"stage": "start_setup_validation"},
                "reason_failed": "previous error",
            },
        )

        usecase = StartSetupUseCase()
        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertEqual(onboarding.progress, 0)
        self.assertEqual(onboarding.current_step, "")
        self.assertIsNone(onboarding.crawler_result)
        self.assertFalse(onboarding.completed)
        self.assertNotIn("last_failure", onboarding.config)
        self.assertNotIn("reason_failed", onboarding.config)

    def test_try_link_project_finds_existing_project(self):
        """_try_link_project should link a matching project."""
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        onboarding = ProjectOnboarding.objects.create(vtex_account="mystore")

        StartSetupUseCase._try_link_project(onboarding)

        self.assertEqual(onboarding.project, project)

    def test_try_link_project_does_nothing_when_no_project(self):
        """_try_link_project should do nothing if no project matches."""
        onboarding = ProjectOnboarding.objects.create(vtex_account="nostore")

        StartSetupUseCase._try_link_project(onboarding)

        self.assertIsNone(onboarding.project)

    def test_try_link_project_skips_when_already_linked(self):
        """_try_link_project should skip if a project is already linked."""
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore", project=project
        )

        StartSetupUseCase._try_link_project(onboarding)
        self.assertEqual(onboarding.project, project)

    def test_try_link_project_raises_on_multiple_projects(self):
        """_try_link_project should raise when multiple projects share a vtex_account."""
        Project.objects.create(name="First", uuid=uuid4(), vtex_account="mystore")
        Project.objects.create(name="Second", uuid=uuid4(), vtex_account="mystore")
        onboarding = ProjectOnboarding.objects.create(vtex_account="mystore")

        with self.assertRaises(Project.MultipleObjectsReturned):
            StartSetupUseCase._try_link_project(onboarding)

    @patch("retail.projects.usecases.start_setup.task_wait_and_start_crawl")
    def test_stores_channel_data_in_config(self, mock_task):
        """When channel_data is provided, it should be stored in onboarding config."""
        dto = StartSetupDTO(
            vtex_account="mystore",
            crawl_url="https://www.mystore.com.br/",
            channel="wpp-cloud",
            channel_data={
                "auth_code": "abc123",
                "waba_id": "waba456",
                "phone_number_id": "phone789",
            },
        )

        usecase = StartSetupUseCase()
        usecase.execute(dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        channel_data = onboarding.config["channels"]["wpp-cloud"]["channel_data"]
        self.assertEqual(channel_data["auth_code"], "abc123")
        self.assertEqual(channel_data["waba_id"], "waba456")
        self.assertEqual(channel_data["phone_number_id"], "phone789")
