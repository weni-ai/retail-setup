from django.test import TestCase

from uuid import uuid4

from retail.projects.models import Project
from retail.agents.push.models import Agent
from retail.agents.push.usecases import ListAgentsUseCase


class ListAgentsUseCaseTest(TestCase):
    def setUp(self):
        self.project1 = Project.objects.create(name="Project 1", uuid=uuid4())
        self.project2 = Project.objects.create(name="Project 2", uuid=uuid4())

        Agent.objects.create(name="Agente 1", project=self.project1, is_oficial=False)
        Agent.objects.create(name="Agente 2", project=self.project1, is_oficial=True)

        Agent.objects.create(name="Agente 3", project=self.project2, is_oficial=False)
        Agent.objects.create(name="Agente 4", project=self.project2, is_oficial=True)

    def test_execute_with_project_uuid(self):
        result = ListAgentsUseCase.execute(str(self.project1.uuid))
        self.assertEqual(result.count(), 3)
        self.assertTrue(
            all(
                agent.is_oficial or str(agent.project.uuid) == str(self.project1.uuid)
                for agent in result
            )
        )

    def test_execute_with_none_project_uuid(self):
        result = ListAgentsUseCase.execute(None)
        self.assertTrue(all(agent.is_oficial for agent in result))

    def test_execute_with_nonexistent_project_uuid(self):
        result = ListAgentsUseCase.execute(str(uuid4()))
        self.assertTrue(all(agent.is_oficial for agent in result))
