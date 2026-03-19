from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase, override_settings

from retail.projects.usecases.onboarding_agents.agents import AbandonedCartAgent
from retail.projects.usecases.onboarding_agents.base import AgentContext


FAKE_AGENT_UUID = str(uuid4())


@override_settings(ABANDONED_CART_AGENT_UUID=FAKE_AGENT_UUID)
class TestAbandonedCartAgent(TestCase):
    def setUp(self):
        self.context = AgentContext(
            project_uuid=str(uuid4()),
            vtex_account="mystore",
            app_uuid=str(uuid4()),
            channel_uuid=str(uuid4()),
        )
        self.mock_nexus_service = MagicMock()

    def test_raises_when_no_uuid_configured(self):
        agent = AbandonedCartAgent()
        agent.uuid = ""

        with self.assertRaises(ValueError) as ctx:
            agent.integrate(self.context, self.mock_nexus_service)

        self.assertIn("has no UUID", str(ctx.exception))

    def test_raises_when_no_app_uuid_in_context(self):
        agent = AbandonedCartAgent()
        context = AgentContext(
            project_uuid=str(uuid4()),
            vtex_account="mystore",
            app_uuid=None,
            channel_uuid=str(uuid4()),
        )

        with self.assertRaises(ValueError) as ctx:
            agent.integrate(context, self.mock_nexus_service)

        self.assertIn("requires app_uuid", str(ctx.exception))

    def test_raises_when_no_channel_uuid_in_context(self):
        agent = AbandonedCartAgent()
        context = AgentContext(
            project_uuid=str(uuid4()),
            vtex_account="mystore",
            app_uuid=str(uuid4()),
            channel_uuid=None,
        )

        with self.assertRaises(ValueError) as ctx:
            agent.integrate(context, self.mock_nexus_service)

        self.assertIn("requires app_uuid", str(ctx.exception))

    @patch("retail.projects.usecases.onboarding_agents.agents.Agent.objects.get")
    def test_raises_when_agent_not_found_in_db(self, mock_get):
        from retail.agents.domains.agent_management.models import Agent

        mock_get.side_effect = Agent.DoesNotExist

        agent = AbandonedCartAgent()

        with self.assertRaises(ValueError) as ctx:
            agent.integrate(self.context, self.mock_nexus_service)

        self.assertIn("not found in database", str(ctx.exception))

    @patch("retail.projects.usecases.onboarding_agents.agents.AssignAgentUseCase")
    @patch("retail.projects.usecases.onboarding_agents.agents.Agent.objects.get")
    def test_calls_assign_use_case_with_correct_args(
        self, mock_agent_get, mock_assign_cls
    ):
        template_uuid = uuid4()
        mock_agent = MagicMock()
        mock_agent.templates.values_list.return_value = [template_uuid]
        mock_agent_get.return_value = mock_agent

        mock_integrated = MagicMock()
        mock_integrated.uuid = uuid4()
        mock_assign = MagicMock()
        mock_assign.execute.return_value = mock_integrated
        mock_assign_cls.return_value = mock_assign

        agent = AbandonedCartAgent()
        result = agent.integrate(self.context, self.mock_nexus_service)

        mock_assign.execute.assert_called_once_with(
            agent=mock_agent,
            project_uuid=self.context.project_uuid,
            app_uuid=self.context.app_uuid,
            channel_uuid=self.context.channel_uuid,
            credentials={},
            include_templates=[template_uuid],
        )
        self.assertIn("integrated_agent_uuid", result)

    @patch("retail.projects.usecases.onboarding_agents.agents.AssignAgentUseCase")
    @patch("retail.projects.usecases.onboarding_agents.agents.Agent.objects.get")
    def test_returns_integrated_agent_uuid(self, mock_agent_get, mock_assign_cls):
        mock_agent = MagicMock()
        mock_agent.templates.values_list.return_value = []
        mock_agent_get.return_value = mock_agent

        expected_uuid = uuid4()
        mock_integrated = MagicMock()
        mock_integrated.uuid = expected_uuid
        mock_assign = MagicMock()
        mock_assign.execute.return_value = mock_integrated
        mock_assign_cls.return_value = mock_assign

        agent = AbandonedCartAgent()
        result = agent.integrate(self.context, self.mock_nexus_service)

        self.assertEqual(result["integrated_agent_uuid"], str(expected_uuid))
