from unittest.mock import Mock
from uuid import uuid4

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.agents.exceptions import AgentFileNotSent
from retail.agents.models import Agent, PreApprovedTemplate
from retail.agents.usecases import PushAgentUseCase
from retail.projects.models import Project


class PushAgentUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.agent_slug = "test-agent"
        self.agent_name = "Test Agent"
        self.agent_description = "Description"
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

    def test_update_or_create_agent_creates(self):
        payload = {
            "name": self.agent_name,
            "rules": {},
            "pre_processing": {},
            "description": self.agent_description,
        }
        agent, created = self.usecase._update_or_create_agent(
            payload, self.agent_slug, self.project
        )
        self.assertTrue(created)
        self.assertEqual(agent.slug, self.agent_slug)
        self.assertEqual(agent.name, self.agent_name)
        self.assertEqual(agent.project, self.project)
        self.assertEqual(agent.credentials, {})

    def test_update_or_create_agent_updates_existing(self):
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name="Old Name",
            project=self.project,
            description="Old Description",
        )
        payload = {
            "name": self.agent_name,
            "rules": {},
            "pre_processing": {},
            "description": self.agent_description,
        }
        updated_agent, created = self.usecase._update_or_create_agent(
            payload, self.agent_slug, self.project
        )
        self.assertFalse(created)
        self.assertEqual(updated_agent.pk, agent.pk)
        self.assertEqual(updated_agent.name, self.agent_name)
        self.assertEqual(updated_agent.description, self.agent_description)

    def test_update_or_create_agent_with_credentials(self):
        payload = {
            "name": self.agent_name,
            "description": self.agent_description,
            "rules": {},
            "pre_processing": {},
            "credentials": [
                {
                    "key": "EXAMPLE_CREDENTIAL",
                    "label": "Label Example",
                    "placeholder": "placeholder-example",
                    "is_confidential": False,
                }
            ],
        }
        awaited_credentials = {
            "EXAMPLE_CREDENTIAL": {
                "is_confidential": False,
                "key": "EXAMPLE_CREDENTIAL",
                "placeholder": "placeholder-example",
                "label": "Label Example",
            }
        }
        agent, created = self.usecase._update_or_create_agent(
            payload, self.agent_slug, self.project
        )
        self.assertTrue(created)
        self.assertEqual(agent.credentials, awaited_credentials)

    def test_upload_to_lambda(self):
        arn = self.usecase._upload_to_lambda(self.uploaded_file, "function_name")
        self.lambda_service_mock.send_file.assert_called_once_with(
            file_obj=self.uploaded_file, function_name="function_name"
        )
        self.assertEqual(arn, "arn:aws:lambda:region:123:function:test")

    def test_assign_arn_to_agent(self):
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name=self.agent_name,
            project=self.project,
            description=self.agent_description,
        )
        arn = "arn:aws:lambda:region:123:function:test"
        agent = self.usecase._assign_arn_to_agent(arn, agent)
        self.assertEqual(agent.lambda_arn, arn)

    def test_create_function_name(self):
        name = self.usecase._create_function_name(self.agent_slug, self.agent_uuid)
        self.assertIn(self.agent_slug, name)
        self.assertIn(self.agent_uuid.hex, name)

    def test_create_pre_approved_templates_creates_and_updates(self):
        agent = Agent.objects.create(
            slug=self.agent_slug,
            name=self.agent_name,
            project=self.project,
            description=self.agent_description,
        )
        payload = {
            "name": self.agent_name,
            "description": self.agent_description,
            "rules": {
                "r1": {
                    "display_name": "d",
                    "template": "template1",
                    "start_condition": "cond",
                    "source": {"entrypoint": "", "path": ""},
                }
            },
            "pre_processing": {},
        }
        self.usecase._update_or_create_pre_approved_templates(agent, payload)
        template = PreApprovedTemplate.objects.get(name="template1", agent=agent)
        self.assertEqual(template.display_name, "d")
        self.assertEqual(template.start_condition, "cond")
        payload["rules"]["r1"]["display_name"] = "novo"
        self.usecase._update_or_create_pre_approved_templates(agent, payload)
        template.refresh_from_db()
        self.assertEqual(template.display_name, "novo")

    def test_execute_success(self):
        payload = {
            "project_uuid": str(self.project.uuid),
            "agents": {
                self.agent_slug: {
                    "name": self.agent_name,
                    "description": self.agent_description,
                    "rules": {
                        "r1": {
                            "display_name": "d",
                            "template": "template1",
                            "start_condition": "cond",
                            "source": {"entrypoint": "", "path": ""},
                        }
                    },
                    "pre_processing": {},
                }
            },
        }
        files = {self.agent_slug: self.uploaded_file}
        agents = self.usecase.execute(payload, files)
        self.assertEqual(len(agents), 1)
        agent = agents[0]
        self.assertEqual(agent.slug, self.agent_slug)
        self.assertEqual(agent.lambda_arn, "arn:aws:lambda:region:123:function:test")
        template = PreApprovedTemplate.objects.get(name="template1", agent=agent)
        self.assertEqual(template.display_name, "d")

    def test_execute_missing_file(self):
        payload = {
            "project_uuid": str(self.project.uuid),
            "agents": {
                self.agent_slug: {
                    "name": self.agent_name,
                    "description": self.agent_description,
                    "rules": {},
                    "pre_processing": {},
                }
            },
        }
        files = {}
        with self.assertRaises(AgentFileNotSent):
            self.usecase.execute(payload, files)
