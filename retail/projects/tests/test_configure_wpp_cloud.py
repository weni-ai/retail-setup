from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.configure_wpp_cloud import (
    PROJECT_CONFIG_AFTER_CREATE,
    PROJECT_CONFIG_AFTER_PERSIST,
    PROJECT_CONFIG_START,
    ConfigureWPPCloudUseCase,
    WPPCloudConfigError,
)


class TestConfigureWPPCloudUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
        )
        self.channel_data = {
            "auth_code": "abc123",
            "waba_id": "waba456",
            "phone_number_id": "phone789",
        }
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wpp-cloud": {"channel_data": self.channel_data}}},
        )
        self.mock_integrations_service = MagicMock()
        self.usecase = ConfigureWPPCloudUseCase(integrations_client=MagicMock())
        self.usecase.integrations_service = self.mock_integrations_service

    def test_full_flow_creates_wpp_cloud_channel(self):
        app_uuid = str(uuid4())
        flow_object_uuid = str(uuid4())
        self.mock_integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": app_uuid,
            "flow_object_uuid": flow_object_uuid,
        }

        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(self.onboarding.progress, PROJECT_CONFIG_AFTER_PERSIST)
        self.assertEqual(
            self.onboarding.config["channels"]["wpp-cloud"]["app_uuid"], app_uuid
        )
        self.assertEqual(
            self.onboarding.config["channels"]["wpp-cloud"]["flow_object_uuid"],
            flow_object_uuid,
        )

    def test_raises_error_when_project_not_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="noproject",
            config={"channels": {"wpp-cloud": {"channel_data": self.channel_data}}},
        )

        with self.assertRaises(WPPCloudConfigError) as ctx:
            self.usecase.execute("noproject")

        self.assertIn("no project linked", str(ctx.exception))

    def test_skips_when_already_configured(self):
        """
        Already-configured onboardings are an idempotent no-op so that
        Celery retries of the wrapping task do not fail mid-pipeline.
        """
        existing_app_uuid = str(uuid4())
        self.onboarding.config = {
            "channels": {
                "wpp-cloud": {
                    "channel_data": self.channel_data,
                    "app_uuid": existing_app_uuid,
                }
            }
        }
        self.onboarding.current_step = "CRAWL"
        self.onboarding.progress = 50
        self.onboarding.save()

        self.usecase.execute("mystore")

        self.mock_integrations_service.create_wpp_cloud_channel.assert_not_called()
        self.onboarding.refresh_from_db()
        # State must not change when we skip
        self.assertEqual(self.onboarding.current_step, "CRAWL")
        self.assertEqual(self.onboarding.progress, 50)
        self.assertEqual(
            self.onboarding.config["channels"]["wpp-cloud"]["app_uuid"],
            existing_app_uuid,
        )

    def test_raises_error_when_no_channel_data(self):
        self.onboarding.config = {"channels": {"wpp-cloud": {}}}
        self.onboarding.save()

        with self.assertRaises(WPPCloudConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("No channel_data found", str(ctx.exception))

    def test_raises_error_when_channel_data_missing_fields(self):
        self.onboarding.config = {
            "channels": {
                "wpp-cloud": {"channel_data": {"auth_code": "abc", "waba_id": ""}}
            }
        }
        self.onboarding.save()

        with self.assertRaises(WPPCloudConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Missing required fields", str(ctx.exception))

    def test_raises_error_when_create_fails(self):
        self.mock_integrations_service.create_wpp_cloud_channel.return_value = None

        with self.assertRaises(WPPCloudConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to create", str(ctx.exception))

    def test_raises_error_when_create_returns_no_app_uuid(self):
        self.mock_integrations_service.create_wpp_cloud_channel.return_value = {
            "flow_object_uuid": str(uuid4()),
        }

        with self.assertRaises(WPPCloudConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("returned no app_uuid", str(ctx.exception))

    def test_calls_integrations_with_correct_channel_data(self):
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": app_uuid,
            "flow_object_uuid": str(uuid4()),
        }

        self.usecase.execute("mystore")

        call_kwargs = (
            self.mock_integrations_service.create_wpp_cloud_channel.call_args.kwargs
        )
        self.assertEqual(call_kwargs["project_uuid"], str(self.project.uuid))
        self.assertEqual(call_kwargs["auth_code"], "abc123")
        self.assertEqual(call_kwargs["waba_id"], "waba456")
        self.assertEqual(call_kwargs["phone_number_id"], "phone789")

    def test_progress_milestones_within_project_config(self):
        """Verifies progress walks the PROJECT_CONFIG start/create/persist milestones."""
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_wpp_cloud_channel.return_value = {
            "app_uuid": app_uuid,
            "flow_object_uuid": str(uuid4()),
        }

        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        # Final progress lands at PROJECT_CONFIG_AFTER_PERSIST
        self.assertEqual(self.onboarding.progress, PROJECT_CONFIG_AFTER_PERSIST)
        # The milestones must be strictly increasing
        self.assertLess(PROJECT_CONFIG_START, PROJECT_CONFIG_AFTER_CREATE)
        self.assertLess(PROJECT_CONFIG_AFTER_CREATE, PROJECT_CONFIG_AFTER_PERSIST)
