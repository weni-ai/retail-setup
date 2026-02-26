from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.integrate_agents import (
    IntegrateAgentsUseCase,
    AgentIntegrationError,
    AGENT_PROGRESS_END,
)
from retail.projects.usecases.onboarding_agents.base import PassiveAgent


class StubPassiveAgent(PassiveAgent):
    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name


class TestIntegrateAgentsUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
            progress=75,
        )
        self.mock_nexus_service = MagicMock()
        self.usecase = IntegrateAgentsUseCase(nexus_client=MagicMock())
        self.usecase.nexus_service = self.mock_nexus_service

    def test_raises_error_when_project_not_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="noproject",
            config={"channels": {"wwc": {}}},
        )

        with self.assertRaises(AgentIntegrationError):
            self.usecase.execute("noproject")

    @patch(
        "retail.projects.usecases.integrate_agents.get_channel_agents",
        return_value=[
            StubPassiveAgent("uuid-1", "Agent A"),
            StubPassiveAgent("uuid-2", "Agent B"),
            StubPassiveAgent("uuid-3", "Agent C"),
        ],
    )
    def test_integrates_all_agents(self, _mock_agents):
        self.mock_nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute("mystore")

        self.assertEqual(self.mock_nexus_service.integrate_agent.call_count, 3)

    @patch(
        "retail.projects.usecases.integrate_agents.get_channel_agents",
        return_value=[
            StubPassiveAgent("uuid-1", "Agent A"),
            StubPassiveAgent("uuid-2", "Agent B"),
        ],
    )
    def test_progress_reaches_100_after_all_agents(self, _mock_agents):
        self.mock_nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute("mystore")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, AGENT_PROGRESS_END)

    @patch(
        "retail.projects.usecases.integrate_agents.get_channel_agents",
        return_value=[],
    )
    def test_skips_when_no_agents(self, _mock_agents):
        self.usecase.execute("mystore")

        self.mock_nexus_service.integrate_agent.assert_not_called()
        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, AGENT_PROGRESS_END)

    @patch(
        "retail.projects.usecases.integrate_agents.get_channel_agents",
        return_value=[
            StubPassiveAgent("uuid-1", "Agent A"),
            StubPassiveAgent("uuid-2", "Agent B"),
        ],
    )
    def test_continues_on_partial_failure(self, _mock_agents):
        self.mock_nexus_service.integrate_agent.side_effect = [None, {"ok": True}]

        self.usecase.execute("mystore")

        self.assertEqual(self.mock_nexus_service.integrate_agent.call_count, 2)
        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, AGENT_PROGRESS_END)

    @patch(
        "retail.projects.usecases.integrate_agents.get_channel_agents",
        return_value=[StubPassiveAgent("uuid-1", "Agent A")],
    )
    def test_passes_correct_project_uuid(self, _mock_agents):
        self.mock_nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute("mystore")

        call_args = self.mock_nexus_service.integrate_agent.call_args
        self.assertEqual(call_args[0][0], str(self.project.uuid))
        self.assertEqual(call_args[0][1], "uuid-1")
