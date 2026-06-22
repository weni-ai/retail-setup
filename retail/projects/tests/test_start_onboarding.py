from unittest.mock import patch
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

    @patch("retail.projects.usecases.start_setup.task_setup_channel_and_start_crawl")
    def test_creates_onboarding_and_schedules_setup_task_when_no_project(
        self, mock_task
    ):
        """When no project exists, should schedule the pre-crawl setup task."""
        usecase = StartSetupUseCase()

        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertIsNone(onboarding.project)
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, 0)
        mock_task.delay.assert_called_once_with(
            "mystore", "https://www.mystore.com.br/"
        )

    @patch("retail.projects.usecases.start_setup.task_setup_channel_and_start_crawl")
    def test_schedules_setup_task_when_project_already_linked(self, mock_task):
        """
        When a project is already linked at start-setup time, the task is
        still dispatched (no inline crawl initiation). The task owns the
        full pre-crawl pipeline regardless of link timing.
        """
        Project.objects.create(name="Test", uuid=uuid4(), vtex_account="mystore")

        usecase = StartSetupUseCase()
        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertIsNotNone(onboarding.project)
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, 0)
        mock_task.delay.assert_called_once_with(
            "mystore", "https://www.mystore.com.br/"
        )

    @patch("retail.projects.usecases.start_setup.task_setup_channel_and_start_crawl")
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
                "background_error": {
                    "stage": "nexus_upload",
                    "error": "previous background error",
                },
            },
        )

        usecase = StartSetupUseCase()
        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        self.assertEqual(onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(onboarding.progress, 0)
        self.assertIsNone(onboarding.crawler_result)
        self.assertFalse(onboarding.completed)
        self.assertNotIn("last_failure", onboarding.config)
        self.assertNotIn("reason_failed", onboarding.config)
        self.assertNotIn("background_error", onboarding.config)

    @patch("retail.projects.usecases.start_setup.task_setup_channel_and_start_crawl")
    def test_reset_clears_previous_channel_app_uuid(self, _mock_task):
        """
        Re-running start-setup must clear previously persisted app_uuid /
        flow_object_uuid so the pre-crawl channel use case can re-create
        the channel with a fresh auth_code.
        """
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={
                "channels": {
                    "wwc": {
                        "app_uuid": "old-app",
                        "flow_object_uuid": "old-flow",
                    },
                    "wpp-cloud": {
                        "channel_data": {"auth_code": "old"},
                        "app_uuid": "old-wpp",
                        "flow_object_uuid": "old-flow-wpp",
                    },
                }
            },
        )

        usecase = StartSetupUseCase()
        usecase.execute(self.dto)

        onboarding = ProjectOnboarding.objects.get(vtex_account="mystore")
        for channel_config in onboarding.config["channels"].values():
            self.assertNotIn("app_uuid", channel_config)
            self.assertNotIn("flow_object_uuid", channel_config)

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

    def test_try_link_project_relinks_when_onboarding_points_to_inactive_project(self):
        """_try_link_project should link to the active project when onboarding is stale."""
        inactive_project = Project.all_objects.create(
            name="Inactive",
            uuid=uuid4(),
            vtex_account="mystore",
            is_active=False,
        )
        active_project = Project.objects.create(
            name="Active",
            uuid=uuid4(),
            vtex_account="mystore",
        )
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=inactive_project,
        )

        StartSetupUseCase._try_link_project(onboarding)

        onboarding.refresh_from_db()
        self.assertEqual(onboarding.project, active_project)

    def test_execute_creates_new_onboarding_when_only_inactive_exists(self):
        """start-setup must not reuse channel config from a soft-deleted onboarding."""
        inactive_onboarding = ProjectOnboarding.all_objects.create(
            vtex_account="mystore",
            is_active=False,
            config={"channels": {"wwc": {"app_uuid": "stale"}}},
        )

        with patch(
            "retail.projects.usecases.start_setup.task_setup_channel_and_start_crawl"
        ):
            StartSetupUseCase().execute(self.dto)

        active_onboardings = ProjectOnboarding.objects.filter(vtex_account="mystore")
        self.assertEqual(active_onboardings.count(), 1)
        self.assertNotEqual(active_onboardings.get().pk, inactive_onboarding.pk)
        inactive_onboarding.refresh_from_db()
        self.assertFalse(inactive_onboarding.is_active)

    def test_try_link_project_raises_on_multiple_projects(self):
        """_try_link_project should raise when multiple projects share a vtex_account."""
        Project.objects.create(name="First", uuid=uuid4(), vtex_account="mystore")
        Project.objects.create(name="Second", uuid=uuid4(), vtex_account="mystore")
        onboarding = ProjectOnboarding.objects.create(vtex_account="mystore")

        with self.assertRaises(Project.MultipleObjectsReturned):
            StartSetupUseCase._try_link_project(onboarding)

    @patch("retail.projects.usecases.start_setup.task_setup_channel_and_start_crawl")
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
