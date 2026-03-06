from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.suspend_trial_dto import SuspendTrialProjectDTO
from retail.projects.usecases.suspend_trial_project import (
    SuspendTrialProjectUseCase,
    SuspendTrialError,
)


class TestSuspendTrialProjectUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="teststore",
        )
        self.wwc_app_uuid = str(uuid4())
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="teststore",
            project=self.project,
            config={"channels": {"wwc": {"app_uuid": self.wwc_app_uuid}}},
        )

        self.mock_integrations = MagicMock()
        self.mock_connect = MagicMock()

        self.use_case = SuspendTrialProjectUseCase(
            integrations_client=MagicMock(),
            connect_client=MagicMock(),
        )
        self.use_case.integrations_service = self.mock_integrations
        self.use_case.connect_service = self.mock_connect

        self.dto = SuspendTrialProjectDTO(
            project_uuid=str(self.project.uuid),
            conversation_limit=1000,
        )

    def test_full_flow_disables_wwc_and_suspends(self):
        self.mock_integrations.get_channel_app.return_value = {
            "config": {"renderPercentage": 10, "mainColor": "#3d3d3d"},
        }
        self.mock_integrations.configure_channel_app.return_value = {"ok": True}
        self.mock_connect.suspend_trial_project.return_value = {
            "project_uuid": self.dto.project_uuid,
            "suspended": True,
        }

        self.use_case.execute(self.dto)

        self.mock_integrations.get_channel_app.assert_called_once_with(
            "wwc", self.wwc_app_uuid
        )
        configure_call = self.mock_integrations.configure_channel_app.call_args
        self.assertEqual(configure_call[0][0], "wwc")
        self.assertEqual(configure_call[0][1], self.wwc_app_uuid)
        self.assertEqual(configure_call[0][2]["renderPercentage"], 0)
        self.assertEqual(configure_call[0][2]["mainColor"], "#3d3d3d")

        self.mock_connect.suspend_trial_project.assert_called_once_with(
            project_uuid=self.dto.project_uuid,
            conversation_limit=1000,
        )

    def test_skips_wwc_when_no_onboarding(self):
        project_no_onboarding = Project.objects.create(
            name="No Onboarding",
            uuid=uuid4(),
            vtex_account="noboard",
        )
        dto = SuspendTrialProjectDTO(
            project_uuid=str(project_no_onboarding.uuid),
            conversation_limit=1000,
        )
        self.mock_connect.suspend_trial_project.return_value = {
            "project_uuid": dto.project_uuid,
            "suspended": True,
        }

        self.use_case.execute(dto)

        self.mock_integrations.get_channel_app.assert_not_called()
        self.mock_connect.suspend_trial_project.assert_called_once()

    def test_skips_wwc_when_no_app_uuid_in_config(self):
        self.onboarding.config = {"channels": {"wwc": {}}}
        self.onboarding.save()

        self.mock_connect.suspend_trial_project.return_value = {
            "project_uuid": self.dto.project_uuid,
            "suspended": True,
        }

        self.use_case.execute(self.dto)

        self.mock_integrations.get_channel_app.assert_not_called()
        self.mock_connect.suspend_trial_project.assert_called_once()

    def test_raises_error_when_project_not_found(self):
        dto = SuspendTrialProjectDTO(
            project_uuid=str(uuid4()),
            conversation_limit=1000,
        )

        with self.assertRaises(SuspendTrialError) as ctx:
            self.use_case.execute(dto)

        self.assertIn("Project not found", str(ctx.exception))

    def test_raises_error_when_get_channel_app_fails(self):
        self.mock_integrations.get_channel_app.return_value = None

        with self.assertRaises(SuspendTrialError) as ctx:
            self.use_case.execute(self.dto)

        self.assertIn("Failed to retrieve WWC channel config", str(ctx.exception))

    def test_raises_error_when_configure_channel_fails(self):
        self.mock_integrations.get_channel_app.return_value = {
            "config": {"renderPercentage": 10},
        }
        self.mock_integrations.configure_channel_app.return_value = None

        with self.assertRaises(SuspendTrialError) as ctx:
            self.use_case.execute(self.dto)

        self.assertIn("Failed to disable WWC channel", str(ctx.exception))

    def test_raises_error_when_connect_suspend_fails(self):
        self.mock_integrations.get_channel_app.return_value = {
            "config": {"renderPercentage": 10},
        }
        self.mock_integrations.configure_channel_app.return_value = {"ok": True}
        self.mock_connect.suspend_trial_project.side_effect = Exception(
            "Connection refused"
        )

        with self.assertRaises(Exception):
            self.use_case.execute(self.dto)

    def test_handles_empty_onboarding_config(self):
        self.onboarding.config = {}
        self.onboarding.save()

        self.mock_connect.suspend_trial_project.return_value = {
            "project_uuid": self.dto.project_uuid,
            "suspended": True,
        }

        self.use_case.execute(self.dto)

        self.mock_integrations.get_channel_app.assert_not_called()
        self.mock_connect.suspend_trial_project.assert_called_once()

    def test_preserves_existing_config_keys_when_disabling_wwc(self):
        self.mock_integrations.get_channel_app.return_value = {
            "config": {
                "renderPercentage": 10,
                "mainColor": "#3d3d3d",
                "title": "Support Chat",
                "displayUnreadCount": True,
            },
        }
        self.mock_integrations.configure_channel_app.return_value = {"ok": True}
        self.mock_connect.suspend_trial_project.return_value = {
            "project_uuid": self.dto.project_uuid,
            "suspended": True,
        }

        self.use_case.execute(self.dto)

        updated_config = self.mock_integrations.configure_channel_app.call_args[0][2]
        self.assertEqual(updated_config["renderPercentage"], 0)
        self.assertEqual(updated_config["mainColor"], "#3d3d3d")
        self.assertEqual(updated_config["title"], "Support Chat")
        self.assertTrue(updated_config["displayUnreadCount"])
