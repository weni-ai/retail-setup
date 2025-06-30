from django.test import TestCase

from unittest.mock import patch, MagicMock

from uuid import uuid4

from retail.agents.assign.usecases.retrieve_integrated_agent import (
    RetrieveIntegratedAgentUseCase,
)
from rest_framework.exceptions import NotFound


class RetrieveIntegratedAgentUseCaseTest(TestCase):
    def setUp(self):
        self.usecase = RetrieveIntegratedAgentUseCase()
        self.pk = uuid4()

    @patch("retail.agents.assign.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_get_integrated_agent_returns_agent(self, mock_integrated_agent_cls):
        mock_agent = MagicMock()
        mock_integrated_agent_cls.objects.get.return_value = mock_agent

        result = self.usecase._get_integrated_agent(self.pk)
        mock_integrated_agent_cls.objects.get.assert_called_once_with(
            uuid=self.pk, is_active=True
        )
        self.assertEqual(result, mock_agent)

    @patch("retail.agents.assign.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_get_integrated_agent_raises_not_found(self, mock_integrated_agent_cls):
        class DoesNotExist(Exception):
            pass

        mock_integrated_agent_cls.DoesNotExist = DoesNotExist
        mock_integrated_agent_cls.objects.get.side_effect = DoesNotExist()

        with self.assertRaises(NotFound) as context:
            self.usecase._get_integrated_agent(self.pk)
        self.assertIn("Assigned agent not found", str(context.exception))

    @patch("retail.agents.assign.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_execute_returns_agent(self, mock_integrated_agent_cls):
        mock_agent = MagicMock()
        mock_integrated_agent_cls.objects.get.return_value = mock_agent

        result = self.usecase.execute(self.pk)
        mock_integrated_agent_cls.objects.get.assert_called_once_with(
            uuid=self.pk, is_active=True
        )
        self.assertEqual(result, mock_agent)

    @patch("retail.agents.assign.usecases.retrieve_integrated_agent.IntegratedAgent")
    def test_execute_raises_not_found(self, mock_integrated_agent_cls):
        class DoesNotExist(Exception):
            pass

        mock_integrated_agent_cls.DoesNotExist = DoesNotExist
        mock_integrated_agent_cls.objects.get.side_effect = DoesNotExist()

        with self.assertRaises(NotFound):
            self.usecase.execute(self.pk)
