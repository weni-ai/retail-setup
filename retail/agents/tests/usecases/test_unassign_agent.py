from uuid import uuid4

from django.test import TestCase

from rest_framework.exceptions import NotFound

from retail.agents.models import Agent, IntegratedAgent
from retail.projects.models import Project
from retail.agents.usecases import UnassignAgentUseCase


class UnassignAgentUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            is_oficial=True,
            lambda_arn="arn:aws:lambda:...",
            name="Agent",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
        )
        self.use_case = UnassignAgentUseCase()

    def test_execute_success(self):
        self.assertTrue(
            IntegratedAgent.objects.filter(
                agent=self.agent, project=self.project
            ).exists()
        )
        self.use_case.execute(self.agent, str(self.project.uuid))
        self.assertFalse(
            IntegratedAgent.objects.filter(
                agent=self.agent, project=self.project
            ).exists()
        )

    def test_execute_not_found(self):
        self.integrated_agent.delete()
        with self.assertRaises(NotFound) as context:
            self.use_case.execute(self.agent, str(self.project.uuid))
        self.assertIn("Integrated agent not found", str(context.exception))
