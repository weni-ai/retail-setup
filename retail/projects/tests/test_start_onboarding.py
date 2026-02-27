from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_dto import StartOnboardingDTO
from retail.projects.usecases.start_onboarding import StartOnboardingUseCase


class TestStartOnboardingUseCase(TestCase):
    def setUp(self):
        self.dto = StartOnboardingDTO(
            vtex_account="mystore",
            crawl_url="https://www.mystore.com.br/",
            channel="wwc",
        )

    @patch("retail.projects.usecases.start_onboarding.task_wait_and_start_crawl")
    def test_creates_onboarding_and_schedules_wait_task_when_no_project(
        self, mock_task
    ):
        """When no project exists, should schedule task_wait_and_start_crawl."""
        usecase = StartOnboardingUseCase()

        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertIsNone(onboarding.project)
        mock_task.delay.assert_called_once_with(
            "mystore", "https://www.mystore.com.br/"
        )

    @patch("retail.projects.usecases.start_onboarding.StartCrawlUseCase")
    def test_starts_crawl_immediately_when_project_exists(self, mock_crawl_cls):
        """When a project is linked, should start crawl immediately."""
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

        mock_crawl_instance = MagicMock()
        mock_crawl_cls.return_value = mock_crawl_instance

        usecase = StartOnboardingUseCase()
        usecase.start_crawl_usecase = mock_crawl_instance

        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertEqual(onboarding.project, project)
        mock_crawl_instance.execute.assert_called_once_with(
            "mystore", "https://www.mystore.com.br/"
        )

    @patch("retail.projects.usecases.start_onboarding.task_wait_and_start_crawl")
    def test_resets_existing_onboarding_on_retry(self, mock_task):
        """When an onboarding already exists, should reset transient fields."""
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            current_step="CRAWL",
            progress=80,
            crawler_result=ProjectOnboarding.SUCCESS,
            completed=True,
        )

        usecase = StartOnboardingUseCase()
        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertEqual(onboarding.progress, 0)
        self.assertEqual(onboarding.current_step, "")
        self.assertIsNone(onboarding.crawler_result)
        self.assertFalse(onboarding.completed)

    def test_try_link_project_finds_existing_project(self):
        """_try_link_project should link a matching project."""
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        onboarding = ProjectOnboarding.objects.create(vtex_account="mystore")

        StartOnboardingUseCase._try_link_project(onboarding)

        self.assertEqual(onboarding.project, project)

    def test_try_link_project_does_nothing_when_no_project(self):
        """_try_link_project should do nothing if no project matches."""
        onboarding = ProjectOnboarding.objects.create(vtex_account="nostore")

        StartOnboardingUseCase._try_link_project(onboarding)

        self.assertIsNone(onboarding.project)

    def test_try_link_project_skips_when_already_linked(self):
        """_try_link_project should skip if a project is already linked."""
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore", project=project
        )

        # Should not raise or change anything
        StartOnboardingUseCase._try_link_project(onboarding)
        self.assertEqual(onboarding.project, project)

    def test_try_link_project_raises_on_multiple_projects(self):
        """_try_link_project should raise when multiple projects share a vtex_account."""
        Project.objects.create(name="First", uuid=uuid4(), vtex_account="mystore")
        Project.objects.create(name="Second", uuid=uuid4(), vtex_account="mystore")
        onboarding = ProjectOnboarding.objects.create(vtex_account="mystore")

        with self.assertRaises(Project.MultipleObjectsReturned):
            StartOnboardingUseCase._try_link_project(onboarding)
