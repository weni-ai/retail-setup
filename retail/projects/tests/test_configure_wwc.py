from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.configure_wwc import (
    PROJECT_CONFIG_AFTER_CONFIGURE,
    PROJECT_CONFIG_AFTER_CREATE,
    PROJECT_CONFIG_AFTER_PERSIST,
    PROJECT_CONFIG_START,
    ConfigureWWCUseCase,
    WWCConfigError,
)


class TestConfigureWWCUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
        )
        self.mock_integrations_service = MagicMock()
        self.usecase = ConfigureWWCUseCase(integrations_client=MagicMock())
        self.usecase.integrations_service = self.mock_integrations_service

    def test_full_flow_creates_and_configures_wwc(self):
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_channel_app.return_value = {
            "uuid": app_uuid,
            "code": "wwc",
        }
        self.mock_integrations_service.configure_channel_app.return_value = {
            "uuid": app_uuid,
            "script": "https://example.com/script.js",
        }

        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_step, "PROJECT_CONFIG")
        self.assertEqual(self.onboarding.progress, PROJECT_CONFIG_AFTER_PERSIST)
        self.assertEqual(
            self.onboarding.config["channels"]["wwc"]["app_uuid"], app_uuid
        )

    def test_raises_error_when_project_not_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="noproject",
        )

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("noproject")

        self.assertIn("no project linked", str(ctx.exception))

    def test_skips_when_wwc_already_configured(self):
        """
        Already-configured onboardings are an idempotent no-op so that
        Celery retries of the wrapping task do not fail mid-pipeline.
        """
        existing_app_uuid = str(uuid4())
        self.onboarding.config = {"channels": {"wwc": {"app_uuid": existing_app_uuid}}}
        self.onboarding.current_step = "CRAWL"
        self.onboarding.progress = 50
        self.onboarding.save()

        self.usecase.execute("mystore")

        self.mock_integrations_service.create_channel_app.assert_not_called()
        self.mock_integrations_service.configure_channel_app.assert_not_called()
        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_step, "CRAWL")
        self.assertEqual(self.onboarding.progress, 50)
        self.assertEqual(
            self.onboarding.config["channels"]["wwc"]["app_uuid"], existing_app_uuid
        )

    def test_raises_error_when_create_fails(self):
        self.mock_integrations_service.create_channel_app.return_value = None

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to create", str(ctx.exception))

    def test_raises_error_when_create_returns_no_uuid(self):
        self.mock_integrations_service.create_channel_app.return_value = {
            "code": "wwc",
        }

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("returned no uuid", str(ctx.exception))

    def test_raises_error_when_configure_fails(self):
        self.mock_integrations_service.create_channel_app.return_value = {
            "uuid": str(uuid4()),
        }
        self.mock_integrations_service.configure_channel_app.return_value = None

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to configure", str(ctx.exception))

    def test_calls_create_with_correct_args(self):
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_channel_app.return_value = {
            "uuid": app_uuid,
        }
        self.mock_integrations_service.configure_channel_app.return_value = {
            "uuid": app_uuid,
        }

        self.usecase.execute("mystore")

        create_call = self.mock_integrations_service.create_channel_app.call_args
        self.assertEqual(create_call[0][0], "wwc")
        self.assertEqual(create_call[0][1], str(self.project.uuid))

    def test_calls_configure_with_correct_args(self):
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_channel_app.return_value = {
            "uuid": app_uuid,
        }
        self.mock_integrations_service.configure_channel_app.return_value = {
            "uuid": app_uuid,
        }

        self.usecase.execute("mystore")

        configure_call = self.mock_integrations_service.configure_channel_app.call_args
        self.assertEqual(configure_call[0][0], "wwc")
        self.assertEqual(configure_call[0][1], app_uuid)

    def test_configure_uses_default_bottom_right_position(self):
        """The widget defaults to bottom-right, matching how it renders today."""
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_channel_app.return_value = {
            "uuid": app_uuid,
        }
        self.mock_integrations_service.configure_channel_app.return_value = {
            "uuid": app_uuid,
        }

        self.usecase.execute("mystore")

        configure_call = self.mock_integrations_service.configure_channel_app.call_args
        channel_config = configure_call[0][2]
        self.assertEqual(channel_config["position"], "bottom-right")

    def test_progress_milestones_within_project_config(self):
        """Progress walks the PROJECT_CONFIG start/create/configure/persist milestones."""
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_channel_app.return_value = {
            "uuid": app_uuid,
        }
        self.mock_integrations_service.configure_channel_app.return_value = {
            "uuid": app_uuid,
        }

        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, PROJECT_CONFIG_AFTER_PERSIST)
        self.assertLess(PROJECT_CONFIG_START, PROJECT_CONFIG_AFTER_CREATE)
        self.assertLess(PROJECT_CONFIG_AFTER_CREATE, PROJECT_CONFIG_AFTER_CONFIGURE)
        self.assertLess(PROJECT_CONFIG_AFTER_CONFIGURE, PROJECT_CONFIG_AFTER_PERSIST)
