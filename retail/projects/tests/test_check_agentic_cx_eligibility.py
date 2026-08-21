from uuid import uuid4
from unittest.mock import patch

from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.agentic_cx_script import (
    CheckAgenticCxEligibilityUseCase,
)


class TestCheckAgenticCxEligibilityUseCase(TestCase):
    def setUp(self):
        self._task_patcher = patch(
            "retail.projects.agentic_cx_tasks.task_ensure_agentic_cx_script_active"
        )
        self._task_patcher.start()
        self.addCleanup(self._task_patcher.stop)

        self.vtex_account = "mystore"
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account=self.vtex_account
        )
        self.use_case = CheckAgenticCxEligibilityUseCase()

    def test_eligible_when_onboarding_completed(self):
        ProjectOnboarding.objects.create(
            vtex_account=self.vtex_account,
            project=self.project,
            completed=True,
        )

        self.assertTrue(self.use_case.execute(self.vtex_account))

    def test_eligible_when_channel_has_app_uuid(self):
        ProjectOnboarding.objects.create(
            vtex_account=self.vtex_account,
            project=self.project,
            completed=False,
            config={"channels": {"wwc": {"app_uuid": "wwc-app-uuid"}}},
        )

        self.assertTrue(self.use_case.execute(self.vtex_account))

    def test_eligible_when_active_integrated_agent_exists(self):
        ProjectOnboarding.objects.create(
            vtex_account=self.vtex_account,
            project=self.project,
            completed=False,
        )
        agent = Agent.objects.create(
            name="Abandoned Cart",
            slug="abandoned-cart",
            description="",
            project=self.project,
        )
        IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            is_active=True,
        )

        self.assertTrue(self.use_case.execute(self.vtex_account))

    def test_not_eligible_when_channels_hold_only_channel_data(self):
        ProjectOnboarding.objects.create(
            vtex_account=self.vtex_account,
            project=self.project,
            completed=False,
            config={
                "channels": {
                    "wpp-cloud": {
                        "channel_data": {
                            "auth_code": "abc",
                            "waba_id": "waba-1",
                        }
                    }
                }
            },
        )

        self.assertFalse(self.use_case.execute(self.vtex_account))

    def test_not_eligible_when_only_inactive_agent_exists(self):
        ProjectOnboarding.objects.create(
            vtex_account=self.vtex_account,
            project=self.project,
            completed=False,
        )
        agent = Agent.objects.create(
            name="Abandoned Cart",
            slug="abandoned-cart",
            description="",
            project=self.project,
        )
        IntegratedAgent.objects.create(
            agent=agent,
            project=self.project,
            is_active=False,
        )

        self.assertFalse(self.use_case.execute(self.vtex_account))

    def test_not_eligible_when_onboarding_does_not_exist(self):
        self.assertFalse(self.use_case.execute(self.vtex_account))

    def test_not_eligible_when_vtex_account_is_empty(self):
        self.assertFalse(self.use_case.execute(""))

    def test_not_eligible_when_app_uuid_is_blank(self):
        ProjectOnboarding.objects.create(
            vtex_account=self.vtex_account,
            project=self.project,
            completed=False,
            config={"channels": {"wwc": {"app_uuid": ""}}},
        )

        self.assertFalse(self.use_case.execute(self.vtex_account))

    def test_not_eligible_when_project_is_not_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="orphan-store",
            completed=False,
        )

        self.assertFalse(self.use_case.execute("orphan-store"))
