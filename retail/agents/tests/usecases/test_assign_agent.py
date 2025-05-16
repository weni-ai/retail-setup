import uuid

from unittest.mock import patch, MagicMock

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

    def test_generate_client_secret_length(self):
        secret = self.use_case._generate_client_secret()
        self.assertTrue(len(secret) > 32)

    def test_hash_secret_format_and_uniqueness(self):
        client_secret = "my_secret"
        hash1 = self.use_case._hash_secret(client_secret)
        hash2 = self.use_case._hash_secret(client_secret)

        self.assertIn(":", hash1)

        salt1, hashed1 = hash1.split(":")

        self.assertNotEqual(hash1, hash2)
        self.assertEqual(len(salt1), 32)
        self.assertEqual(len(hashed1), 64)

    def test_create_integrated_agent(self):
        hashed_secret = "salt:hash"
        integrated_agent = self.use_case._create_integrated_agent(
            agent=self.agent,
            project=self.project,
            hashed_client_secret=hashed_secret,
        )
        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)
        self.assertEqual(integrated_agent.client_secret, hashed_secret)
        self.assertEqual(integrated_agent.lambda_arn, self.agent.lambda_arn)

    @patch.object(AssignAgentUseCase, "_create_integrated_agent")
    @patch.object(AssignAgentUseCase, "_hash_secret")
    @patch.object(AssignAgentUseCase, "_generate_client_secret")
    @patch.object(AssignAgentUseCase, "_get_project")
    def test_execute_success(
        self,
        mock_get_project,
        mock_generate_secret,
        mock_hash_secret,
        mock_create_integrated,
    ):
        mock_get_project.return_value = self.project
        mock_generate_secret.return_value = "plain_secret"
        mock_hash_secret.return_value = "salt:hashed"
        mock_integrated = MagicMock(spec=IntegratedAgent)
        mock_create_integrated.return_value = mock_integrated

        result = self.use_case.execute(self.agent, self.project.uuid)
        self.assertEqual(result, (mock_integrated, "plain_secret"))
        mock_get_project.assert_called_once_with(self.project.uuid)
        mock_generate_secret.assert_called_once()
        mock_hash_secret.assert_called_once_with("plain_secret")
        mock_create_integrated.assert_called_once_with(
            agent=self.agent,
            project=self.project,
            hashed_client_secret="salt:hashed",
        )

    def test_execute_integration(self):
        integrated_agent, client_secret = self.use_case.execute(
            self.agent, self.project.uuid
        )
        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)
        self.assertIn(":", integrated_agent.client_secret)
        self.assertTrue(len(client_secret) > 32)

    def test_execute_project_not_found(self):
        random_uuid = uuid.uuid4()
        with self.assertRaises(NotFound):
            self.use_case.execute(self.agent, random_uuid)
