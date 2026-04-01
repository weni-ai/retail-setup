from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.configure_wpp_cloud import (
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
        self.assertEqual(self.onboarding.current_step, "NEXUS_CONFIG")
        self.assertEqual(self.onboarding.progress, 10)
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

    def test_raises_error_when_already_configured(self):
        self.onboarding.config = {"channels": {"wpp-cloud": {"app_uuid": str(uuid4())}}}
        self.onboarding.save()

        with self.assertRaises(WPPCloudConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("already configured", str(ctx.exception))

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

    def test_progress_at_3_after_channel_created(self):
        """Progress should be 3% right after channel creation, before persist."""
        app_uuid = str(uuid4())

        def capture_progress(*args, **kwargs):
            self.onboarding.refresh_from_db()
            self.mid_progress = self.onboarding.progress
            return {
                "app_uuid": app_uuid,
                "flow_object_uuid": str(uuid4()),
            }

        self.mock_integrations_service.create_wpp_cloud_channel.side_effect = (
            capture_progress
        )

        self.usecase.execute("mystore")

        self.assertEqual(self.mid_progress, 0)
        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, 10)
