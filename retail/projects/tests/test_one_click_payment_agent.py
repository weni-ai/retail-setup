from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.usecases.onboarding_agents.agents import (
    WPP_FLOW_CREDENTIAL_LABEL,
    WPP_FLOW_CREDENTIAL_NAME,
    OneClickPaymentAgent,
)
from retail.projects.usecases.onboarding_agents.base import AgentContext


class TestOneClickPaymentAgent(TestCase):
    def setUp(self):
        self.project_uuid = str(uuid4())
        self.agent_uuid = str(uuid4())
        self.flow_id = "flow-meta-123"
        self.context = AgentContext(
            project_uuid=self.project_uuid,
            vtex_account="mystore",
            app_uuid=str(uuid4()),
            channel_uuid=str(uuid4()),
            flow_id=self.flow_id,
        )
        self.mock_nexus_service = MagicMock()
        self.mock_nexus_service.integrate_agent.return_value = {"ok": True}
        self.mock_nexus_service.create_agent_credentials.return_value = {
            "created_credentials": [WPP_FLOW_CREDENTIAL_NAME]
        }

    def _make_agent(self) -> OneClickPaymentAgent:
        return OneClickPaymentAgent(uuid=self.agent_uuid, name="One Click Payment")

    def test_full_flow_calls_assign_then_credentials(self):
        agent = self._make_agent()

        result = agent.integrate(self.context, self.mock_nexus_service)

        self.mock_nexus_service.integrate_agent.assert_called_once_with(
            self.project_uuid, self.agent_uuid
        )
        self.mock_nexus_service.create_agent_credentials.assert_called_once_with(
            project_uuid=self.project_uuid,
            agent_uuid=self.agent_uuid,
            credentials=[
                {
                    "name": WPP_FLOW_CREDENTIAL_NAME,
                    "label": WPP_FLOW_CREDENTIAL_LABEL,
                    "is_confidential": True,
                    "value": self.flow_id,
                }
            ],
        )
        self.assertEqual(result["agent_assignment"], {"ok": True})
        self.assertEqual(
            result["credentials"], {"created_credentials": [WPP_FLOW_CREDENTIAL_NAME]}
        )

    def test_raises_when_no_uuid_configured(self):
        agent = OneClickPaymentAgent()

        with self.assertRaises(ValueError) as ctx:
            agent.integrate(self.context, self.mock_nexus_service)

        self.assertIn("has no UUID", str(ctx.exception))
        self.mock_nexus_service.integrate_agent.assert_not_called()

    def test_raises_when_flow_id_missing_in_context(self):
        agent = self._make_agent()
        context = AgentContext(
            project_uuid=self.project_uuid,
            vtex_account="mystore",
            app_uuid=str(uuid4()),
            channel_uuid=str(uuid4()),
            flow_id=None,
        )

        with self.assertRaises(ValueError) as ctx:
            agent.integrate(context, self.mock_nexus_service)

        self.assertIn("flow_id", str(ctx.exception))
        self.mock_nexus_service.integrate_agent.assert_not_called()

    def test_returns_none_when_app_assign_fails(self):
        self.mock_nexus_service.integrate_agent.return_value = None
        agent = self._make_agent()

        result = agent.integrate(self.context, self.mock_nexus_service)

        self.assertIsNone(result)
        self.mock_nexus_service.create_agent_credentials.assert_not_called()

    def test_returns_none_when_credentials_fail(self):
        self.mock_nexus_service.create_agent_credentials.return_value = None
        agent = self._make_agent()

        result = agent.integrate(self.context, self.mock_nexus_service)

        self.assertIsNone(result)
