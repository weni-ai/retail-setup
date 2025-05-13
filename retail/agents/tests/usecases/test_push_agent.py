from unittest.mock import Mock

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from uuid import uuid4

from rest_framework.exceptions import NotFound

from retail.projects.models import Project
from retail.agents.exceptions import AgentFileNotSent
from retail.agents.models import Agent, PreApprovedTemplate
from retail.agents.usecases import PushAgentUseCase


class PushAgentUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.agent_name = "Test Agent"
        self.agent_uuid = uuid4()
        self.file_content = b"print('hello world')"
        self.uploaded_file = SimpleUploadedFile("test.py", self.file_content)
        self.lambda_service_mock = Mock()
        self.lambda_service_mock.send_file.return_value = (
            "arn:aws:lambda:region:123:function:test"
        )
        self.usecase = PushAgentUseCase(lambda_service=self.lambda_service_mock)

    def test_get_project_success(self):
        project = self.usecase._get_project(str(self.project.uuid))
        self.assertEqual(project, self.project)

    def test_get_project_not_found(self):
        with self.assertRaises(NotFound):
            self.usecase._get_project(str(uuid4()))

    def test_get_or_create_agent_creates(self):
        payload = {"name": self.agent_name, "rules": {}, "pre_processing": {}}
        agent, created = self.usecase._get_or_create_agent(payload, self.project)
        self.assertTrue(created)
        self.assertEqual(agent.name, self.agent_name)
        self.assertEqual(agent.project, self.project)

    def test_get_or_create_agent_gets_existing(self):
        Agent.objects.create(name=self.agent_name, project=self.project)
        payload = {"name": self.agent_name, "rules": {}, "pre_processing": {}}
        agent, created = self.usecase._get_or_create_agent(payload, self.project)
        self.assertFalse(created)
        self.assertEqual(agent.name, self.agent_name)

    def test_upload_to_lambda(self):
        arn = self.usecase._upload_to_lambda(self.uploaded_file, "function_name")
        self.lambda_service_mock.send_file.assert_called_once_with(
            file_obj=self.uploaded_file, function_name="function_name"
        )
        self.assertEqual(arn, "arn:aws:lambda:region:123:function:test")

    def test_assign_arn_to_agent(self):
        agent = Agent.objects.create(name=self.agent_name, project=self.project)
        arn = "arn:aws:lambda:region:123:function:test"
        agent = self.usecase._assign_arn_to_agent(arn, agent)
        self.assertEqual(agent.lambda_arn, arn)

    def test_create_function_name(self):
        name = self.usecase._create_function_name(self.agent_name, self.agent_uuid)
        self.assertIn(self.agent_name, name)
        self.assertIn(self.agent_uuid.hex, name)

    def test_create_pre_approved_templates(self):
        agent = Agent.objects.create(name=self.agent_name, project=self.project)
        PreApprovedTemplate.objects.create(name="template1")
        payload = {
            "name": self.agent_name,
            "rules": {
                "r1": {
                    "display_name": "d",
                    "template": "template1",
                    "start_condition": "",
                    "source": {"entrypoint": "", "path": ""},
                }
            },
            "pre_processing": {},
        }
        self.usecase._create_pre_approved_templates(agent, payload)
        self.assertEqual(agent.templates.count(), 1)
        self.assertEqual(agent.templates.first().name, "template1")

    def test_execute_success(self):
        payload = {
            "project_uuid": str(self.project.uuid),
            "agents": {
                "agent1": {
                    "name": self.agent_name,
                    "rules": {
                        "r1": {
                            "display_name": "d",
                            "template": "template1",
                            "start_condition": "",
                            "source": {"entrypoint": "", "path": ""},
                        }
                    },
                    "pre_processing": {},
                }
            },
        }
        PreApprovedTemplate.objects.create(name="template1")
        files = {"agent1": self.uploaded_file}
        agents = self.usecase.execute(payload, files)
        self.assertEqual(len(agents), 1)
        self.assertEqual(agents[0].name, self.agent_name)
        self.assertEqual(
            agents[0].lambda_arn, "arn:aws:lambda:region:123:function:test"
        )
        self.assertEqual(agents[0].templates.first().name, "template1")

    def test_execute_missing_file(self):
        payload = {
            "project_uuid": str(self.project.uuid),
            "agents": {
                "agent1": {"name": self.agent_name, "rules": {}, "pre_processing": {}}
            },
        }
        files = {}
        with self.assertRaises(AgentFileNotSent):
            self.usecase.execute(payload, files)
