from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.configure_wwc import (
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
        )
        self.mock_integrations_service = MagicMock()
        self.usecase = ConfigureWWCUseCase(integrations_client=MagicMock())
        self.usecase.integrations_service = self.mock_integrations_service

    def test_full_flow_creates_and_configures_wwc(self):
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_wwc_app.return_value = {
            "uuid": app_uuid,
            "code": "wwc",
        }
        self.mock_integrations_service.configure_wwc_app.return_value = {
            "uuid": app_uuid,
            "script": "https://example.com/script.js",
        }

        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.current_step, "NEXUS_CONFIG")
        self.assertEqual(self.onboarding.progress, 25)
        self.assertEqual(self.onboarding.config["integrated_apps"]["wwc"], app_uuid)

    def test_raises_error_when_project_not_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="noproject",
        )

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("noproject")

        self.assertIn("no project linked", str(ctx.exception))

    def test_raises_error_when_wwc_already_configured(self):
        self.onboarding.config = {"integrated_apps": {"wwc": str(uuid4())}}
        self.onboarding.save()

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("already configured", str(ctx.exception))

    def test_raises_error_when_create_fails(self):
        self.mock_integrations_service.create_wwc_app.return_value = None

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to create", str(ctx.exception))

    def test_raises_error_when_create_returns_no_uuid(self):
        self.mock_integrations_service.create_wwc_app.return_value = {
            "code": "wwc",
        }

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("returned no uuid", str(ctx.exception))

    def test_raises_error_when_configure_fails(self):
        self.mock_integrations_service.create_wwc_app.return_value = {
            "uuid": str(uuid4()),
        }
        self.mock_integrations_service.configure_wwc_app.return_value = None

        with self.assertRaises(WWCConfigError) as ctx:
            self.usecase.execute("mystore")

        self.assertIn("Failed to configure", str(ctx.exception))

    def test_calls_create_with_correct_project_uuid(self):
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_wwc_app.return_value = {
            "uuid": app_uuid,
        }
        self.mock_integrations_service.configure_wwc_app.return_value = {
            "uuid": app_uuid,
        }

        self.usecase.execute("mystore")

        create_call = self.mock_integrations_service.create_wwc_app.call_args
        self.assertEqual(create_call[0][0], str(self.project.uuid))

    def test_calls_configure_with_correct_app_uuid(self):
        app_uuid = str(uuid4())
        self.mock_integrations_service.create_wwc_app.return_value = {
            "uuid": app_uuid,
        }
        self.mock_integrations_service.configure_wwc_app.return_value = {
            "uuid": app_uuid,
        }

        self.usecase.execute("mystore")

        configure_call = self.mock_integrations_service.configure_wwc_app.call_args
        self.assertEqual(configure_call[0][0], app_uuid)
