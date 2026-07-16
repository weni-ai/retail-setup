from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.agent_builder_helpers import ProjectNotLinkedError
from retail.projects.usecases.configure_agent_builder import (
    ConfigureAgentBuilderUseCase,
    MANAGER_DONE_PROGRESS,
)
from retail.projects.usecases.manager_defaults import (
    MANAGER_DEFAULTS,
    MANAGER_PERSONALITY,
)
from retail.projects.usecases.onboarding_defaults import INSTRUCTIONS_BY_LANGUAGE


class TestConfigureAgentBuilderUseCase(TestCase):
    """Inline path invoked by ``OnboardingOrchestrator``."""

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
            progress=10,
        )
        self.mock_nexus_service = MagicMock()
        self.usecase = ConfigureAgentBuilderUseCase(nexus_client=MagicMock())
        self.usecase.nexus_service = self.mock_nexus_service

    def test_raises_error_when_project_not_linked(self):
        ProjectOnboarding.objects.create(vtex_account="noproject")

        with self.assertRaises(ProjectNotLinkedError):
            self.usecase.execute("noproject")

    def test_bumps_progress_to_manager_done(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, MANAGER_DONE_PROGRESS)

    def test_skips_configure_when_agent_already_exists(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": True, "name": "Mystore Manager"}
        }

        self.usecase.execute("mystore")

        self.mock_nexus_service.check_agent_builder_exists.assert_called_once_with(
            str(self.project.uuid)
        )
        self.mock_nexus_service.configure_agent_attributes.assert_not_called()

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, MANAGER_DONE_PROGRESS)

    def test_configures_agent_when_not_exists(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("mystore")

        self.mock_nexus_service.configure_agent_attributes.assert_called_once()
        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["name"], "Mystore Manager")
        self.assertEqual(payload["agent"]["personality"], MANAGER_PERSONALITY)
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["pt"]["role"])
        self.assertEqual(payload["agent"]["goal"], MANAGER_DEFAULTS["pt"]["goal"])
        self.assertEqual(payload["links"], [])
        self.assertEqual(payload["instructions"], INSTRUCTIONS_BY_LANGUAGE["pt"])

    def test_configures_agent_with_english_fallback(self):
        self.project.language = "ja-jp"
        self.project.save()

        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("mystore")

        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["en"]["role"])
        self.assertEqual(payload["agent"]["goal"], MANAGER_DEFAULTS["en"]["goal"])
        self.assertEqual(payload["instructions"], INSTRUCTIONS_BY_LANGUAGE["en"])

    def test_configures_agent_with_spanish(self):
        self.project.language = "es"
        self.project.save()

        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("mystore")

        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["es"]["role"])
        self.assertEqual(payload["instructions"], INSTRUCTIONS_BY_LANGUAGE["es"])

    def test_configures_agent_when_check_returns_none(self):
        """If the check endpoint fails, we still attempt to configure."""
        self.mock_nexus_service.check_agent_builder_exists.return_value = None
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("mystore")

        self.mock_nexus_service.configure_agent_attributes.assert_called_once()

    def test_configures_agent_with_null_language_falls_back_to_en(self):
        self.project.language = None
        self.project.save()

        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        self.usecase.execute("mystore")

        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["role"], MANAGER_DEFAULTS["en"]["role"])

    def test_does_not_upload_files(self):
        """Inline path must never touch the Nexus upload endpoint."""
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": True}
        }

        self.usecase.execute("mystore")

        self.mock_nexus_service.upload_content_base_files_batch.assert_not_called()
