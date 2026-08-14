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
        self.mock_nexus_service.list_team_agents.return_value = {"agents": []}
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
    def test_stops_on_first_failure(self, _mock_agents):
        self.mock_nexus_service.integrate_agent.side_effect = [None, {"ok": True}]

        with self.assertRaises(AgentIntegrationError):
            self.usecase.execute("mystore")

        self.assertEqual(self.mock_nexus_service.integrate_agent.call_count, 1)
        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, 75)

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

    @patch(
        "retail.projects.usecases.integrate_agents.get_channel_agents",
        return_value=[
            StubPassiveAgent("uuid-1", "Agent A"),
            StubPassiveAgent("uuid-2", "Agent B"),
            StubPassiveAgent("uuid-3", "Agent C"),
        ],
    )
    def test_skips_already_integrated_agents(self, _mock_agents):
        self.mock_nexus_service.list_team_agents.return_value = {
            "agents": [
                {"uuid": "uuid-1", "active": True},
                {"uuid": "uuid-3", "active": True},
            ]
        }
        self.mock_nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute("mystore")

        self.mock_nexus_service.integrate_agent.assert_called_once()
        call_args = self.mock_nexus_service.integrate_agent.call_args
        self.assertEqual(call_args[0][1], "uuid-2")

        self.onboarding.refresh_from_db()
        self.assertEqual(self.onboarding.progress, AGENT_PROGRESS_END)

    @patch(
        "retail.projects.usecases.integrate_agents.get_channel_agents",
        return_value=[
            StubPassiveAgent("uuid-1", "Agent A"),
            StubPassiveAgent("uuid-2", "Agent B"),
        ],
    )
    def test_integrates_all_when_nexus_list_returns_none(self, _mock_agents):
        """When Nexus list fails, all agents should still be integrated."""
        self.mock_nexus_service.list_team_agents.return_value = None
        self.mock_nexus_service.integrate_agent.return_value = {"ok": True}

        self.usecase.execute("mystore")

        self.assertEqual(self.mock_nexus_service.integrate_agent.call_count, 2)

    def test_propagates_flow_id_from_payment_config_to_agent_context(self):
        """When the wpp-cloud config has a published payment flow_id,
        IntegrateAgentsUseCase must hand it to each agent via
        AgentContext.flow_id (needed by OneClickPaymentAgent)."""
        wpp_onboarding = ProjectOnboarding.objects.create(
            vtex_account="wppstore",
            project=Project.objects.create(
                name="WPP Store", uuid=uuid4(), vtex_account="wppstore"
            ),
            config={
                "channels": {
                    "wpp-cloud": {
                        "app_uuid": "app-1",
                        "flow_object_uuid": "channel-1",
                        "payment": {"flow_id": "flow-meta-123"},
                    }
                }
            },
        )

        captured_contexts = []

        class CapturingAgent(StubPassiveAgent):
            def integrate(self, context, nexus_service):
                captured_contexts.append(context)
                return {"ok": True}

        with patch(
            "retail.projects.usecases.integrate_agents.get_channel_agents",
            return_value=[CapturingAgent("uuid-x", "X")],
        ):
            self.usecase.execute("wppstore")

        self.assertEqual(captured_contexts[0].flow_id, "flow-meta-123")
        self.assertEqual(captured_contexts[0].app_uuid, "app-1")
        self.assertEqual(captured_contexts[0].channel_uuid, "channel-1")

        wpp_onboarding.refresh_from_db()
        self.assertEqual(wpp_onboarding.progress, AGENT_PROGRESS_END)
