import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.agents.models import Agent, IntegratedAgent
from retail.agents.usecases import AssignAgentUseCase
from retail.projects.models import Project


class AssignAgentUseCaseTest(TestCase):
    def setUp(self):
        self.use_case = AssignAgentUseCase()
        self.project = Project.objects.create(uuid=uuid.uuid4(), name="Test Project")
        self.agent = Agent.objects.create(
            name="Test Agent", lambda_arn="arn:aws:lambda:fake", project=self.project
        )

    def test_get_project_success(self):
        project = self.use_case._get_project(self.project.uuid)
        self.assertEqual(project, self.project)

    def test_get_project_not_found(self):
        random_uuid = uuid.uuid4()
        with self.assertRaises(NotFound) as ctx:
            self.use_case._get_project(random_uuid)
        self.assertIn("Project not found", str(ctx.exception))

    def test_create_integrated_agent(self):
        integrated_agent = self.use_case._create_integrated_agent(
            agent=self.agent, project=self.project, channel_uuid=uuid.uuid4()
        )
        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)

    @patch.object(AssignAgentUseCase, "_create_integrated_agent")
    @patch.object(AssignAgentUseCase, "_get_project")
    def test_execute_success(
        self,
        mock_get_project,
        mock_create_integrated,
    ):
        mock_get_project.return_value = self.project
        mock_integrated = MagicMock(spec=IntegratedAgent)
        mock_create_integrated.return_value = mock_integrated

        channel_uuid = str(uuid.uuid4())

        self.use_case.execute(
            self.agent, self.project.uuid, str(uuid.uuid4()), channel_uuid, {}, []
        )

        mock_get_project.assert_called_once_with(self.project.uuid)
        mock_create_integrated.assert_called_once_with(
            agent=self.agent, project=self.project, channel_uuid=channel_uuid
        )

    def test_execute_integration(self):
        integrated_agent = self.use_case.execute(
            self.agent, self.project.uuid, str(uuid.uuid4()), str(uuid.uuid4()), {}, []
        )
        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)

    def test_execute_project_not_found(self):
        random_uuid = uuid.uuid4()
        with self.assertRaises(NotFound):
            self.use_case.execute(
                self.agent, random_uuid, str(uuid.uuid4()), str(uuid.uuid4()), {}, []
            )
