from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.agent_builder_helpers import (
    ProjectNotLinkedError,
    ensure_agent_manager_configured,
    load_onboarding_with_linked_project,
)
from retail.projects.usecases.manager_defaults import MANAGER_DEFAULTS


class TestLoadOnboardingWithLinkedProject(TestCase):
    """Shared module-level helper used by both inline and background paths."""

    def test_returns_onboarding_when_project_linked(self):
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        ProjectOnboarding.objects.create(vtex_account="mystore", project=project)

        result = load_onboarding_with_linked_project("mystore")

        self.assertEqual(result.project, project)

    def test_raises_when_project_not_linked(self):
        ProjectOnboarding.objects.create(vtex_account="noproject")

        with self.assertRaises(ProjectNotLinkedError):
            load_onboarding_with_linked_project("noproject")

    def test_raises_does_not_exist_for_unknown_vtex_account(self):
        with self.assertRaises(ProjectOnboarding.DoesNotExist):
            load_onboarding_with_linked_project("unknown")


class TestEnsureAgentManagerConfigured(TestCase):
    """
    Shared idempotent helper. The upload background path calls this
    defensively in case the inline manager step has not yet completed.
    """

    def setUp(self):
        self.project_uuid = str(uuid4())
        self.mock_nexus_service = MagicMock()

    def test_skips_configure_when_agent_already_exists(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": True}
        }

        ensure_agent_manager_configured(
            self.project_uuid, "mystore", "pt-br", self.mock_nexus_service
        )

        self.mock_nexus_service.configure_agent_attributes.assert_not_called()

    def test_configures_when_agent_missing(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        ensure_agent_manager_configured(
            self.project_uuid, "mystore", "pt-br", self.mock_nexus_service
        )

        self.mock_nexus_service.configure_agent_attributes.assert_called_once()
        payload = self.mock_nexus_service.configure_agent_attributes.call_args[0][1]
        self.assertEqual(payload["agent"]["name"], "Mystore Manager")
        self.assertEqual(payload["agent"]["goal"], MANAGER_DEFAULTS["pt"]["goal"])

    def test_configures_when_check_returns_none(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = None
        self.mock_nexus_service.configure_agent_attributes.return_value = {"ok": True}

        ensure_agent_manager_configured(
            self.project_uuid, "mystore", "en-us", self.mock_nexus_service
        )

        self.mock_nexus_service.configure_agent_attributes.assert_called_once()

    def test_logs_failure_when_configure_returns_none(self):
        self.mock_nexus_service.check_agent_builder_exists.return_value = {
            "data": {"has_agent": False}
        }
        self.mock_nexus_service.configure_agent_attributes.return_value = None

        ensure_agent_manager_configured(
            self.project_uuid, "mystore", "pt-br", self.mock_nexus_service
        )

        self.mock_nexus_service.configure_agent_attributes.assert_called_once()
