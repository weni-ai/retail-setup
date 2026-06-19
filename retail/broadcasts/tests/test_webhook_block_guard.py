from unittest.mock import MagicMock, patch

from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_webhook.usecases.webhook import (
    AgentWebhookUseCase,
)


class AgentWebhookProjectBlockGuardTest(TestCase):
    """Covers the project-blocked short-circuit added to the webhook flow."""

    def setUp(self):
        self.cache_handler = MagicMock()
        self.cache_handler.get_cached_agent.return_value = None
        self.use_case = AgentWebhookUseCase(
            active_agent=MagicMock(),
            broadcast=MagicMock(),
            cache=self.cache_handler,
        )

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_returns_none_when_project_is_blocked(self, mock_get):
        agent = MagicMock()
        agent.project = MagicMock()
        agent.project.is_blocked = True
        mock_get.return_value = agent

        result = self.use_case._get_integrated_agent(uuid4())

        self.assertIsNone(result)
        self.cache_handler.set_cached_agent.assert_not_called()

    @patch(
        "retail.agents.domains.agent_webhook.usecases.webhook.IntegratedAgent.objects.get"
    )
    def test_returns_agent_when_project_not_blocked(self, mock_get):
        agent = MagicMock()
        agent.project = MagicMock()
        agent.project.is_blocked = False
        mock_get.return_value = agent

        result = self.use_case._get_integrated_agent(uuid4())

        self.assertIs(result, agent)
        self.cache_handler.set_cached_agent.assert_called_once_with(agent)

    def test_returns_none_when_cached_agent_has_blocked_project(self):
        cached = MagicMock()
        cached.project = MagicMock()
        cached.project.is_blocked = True
        self.cache_handler.get_cached_agent.return_value = cached

        result = self.use_case._get_integrated_agent(uuid4())

        self.assertIsNone(result)
