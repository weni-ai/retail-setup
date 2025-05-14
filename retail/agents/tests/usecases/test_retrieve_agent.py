from django.test import TestCase

from uuid import uuid4

from rest_framework.exceptions import NotFound

from retail.projects.models import Project
from retail.agents.models import Agent
from retail.agents.usecases import RetrieveAgentUseCase


class RetrieveAgentUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project Teste", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agente Teste",
            project=self.project,
            is_oficial=False,
        )

    def test_execute_returns_agent_when_exists(self):
        result = RetrieveAgentUseCase.execute(self.agent.uuid)
        self.assertEqual(result, self.agent)
        self.assertEqual(result.name, "Agente Teste")
        self.assertEqual(result.project, self.project)

    def test_execute_raises_not_found_when_agent_does_not_exist(self):
        fake_uuid = uuid4()
        with self.assertRaises(NotFound) as context:
            RetrieveAgentUseCase.execute(fake_uuid)
        self.assertIn(str(fake_uuid), str(context.exception))
        self.assertIn("Agente not found", str(context.exception))
