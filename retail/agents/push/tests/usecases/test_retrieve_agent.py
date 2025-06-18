from django.test import TestCase

from uuid import uuid4
from unittest.mock import patch, MagicMock

from rest_framework.exceptions import NotFound

from retail.agents.push.usecases import RetrieveAgentUseCase


class RetrieveAgentUseCaseTest(TestCase):
    def setUp(self):
        self.pk = uuid4()
        self.mock_agent = MagicMock()
        self.mock_agent.uuid = self.pk
        self.mock_agent.name = "Agente Teste"
        self.mock_agent.project = MagicMock()
        self.mock_agent.is_oficial = False

    @patch("retail.agents.push.usecases.retrieve_agent.Agent")
    def test_execute_returns_agent_when_exists(self, mock_agent_cls):
        mock_agent_cls.objects.get.return_value = self.mock_agent

        result = RetrieveAgentUseCase.execute(self.pk)
        mock_agent_cls.objects.get.assert_called_once_with(uuid=self.pk)
        self.assertEqual(result, self.mock_agent)
        self.assertEqual(result.name, "Agente Teste")
        self.assertEqual(result.project, self.mock_agent.project)

    @patch("retail.agents.push.usecases.retrieve_agent.Agent")
    def test_execute_raises_not_found_when_agent_does_not_exist(self, mock_agent_cls):
        class DoesNotExist(Exception):
            pass

        mock_agent_cls.DoesNotExist = DoesNotExist
        mock_agent_cls.objects.get.side_effect = DoesNotExist()

        fake_uuid = uuid4()
        with self.assertRaises(NotFound) as context:
            RetrieveAgentUseCase.execute(fake_uuid)
        self.assertIn(str(fake_uuid), str(context.exception))
        self.assertIn("Agent not found", str(context.exception))
