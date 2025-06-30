import uuid

from unittest.mock import MagicMock, patch

from django.test import TestCase

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.assign.models import IntegratedAgent, Credential
from retail.agents.push.models import Agent, PreApprovedTemplate
from retail.agents.assign.usecases import AssignAgentUseCase
from retail.projects.models import Project


class AssignAgentUseCaseTest(TestCase):
    def setUp(self):
        self.use_case = AssignAgentUseCase()
        self.project = Project.objects.create(uuid=uuid.uuid4(), name="Test Project")
        self.agent = Agent.objects.create(
            name="Test Agent",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={
                "api_key": {
                    "label": "API Key",
                    "placeholder": "Enter API key",
                    "is_confidential": True,
                }
            },
        )
        self.agent_oficial = Agent.objects.create(
            name="Test Agent Oficial",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            is_oficial=True,
            credentials={},
        )
        self.agent_not_oficial = Agent.objects.create(
            name="Test Agent Not Oficial",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            is_oficial=False,
            credentials={},
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
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            ignore_templates=[],
        )
        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)
        self.assertTrue(integrated_agent.is_active)

    def test_create_integrated_agent_with_ignore_templates(self):
        template1 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template1",
        )
        template2 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template2",
        )

        ignore_templates = [str(template1.uuid), str(template2.uuid)]
        integrated_agent = self.use_case._create_integrated_agent(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            ignore_templates=ignore_templates,
        )
        self.assertEqual(integrated_agent.ignore_templates, ["template1", "template2"])

    def test_create_integrated_agent_already_exists(self):
        self.use_case._create_integrated_agent(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            ignore_templates=[],
        )

        with self.assertRaises(ValidationError) as ctx:
            self.use_case._create_integrated_agent(
                agent=self.agent,
                project=self.project,
                channel_uuid=uuid.uuid4(),
                ignore_templates=[],
            )
        self.assertIn(
            "This agent is already assigned in this project", str(ctx.exception)
        )

    def test_validate_credentials_success(self):
        credentials = {"api_key": "test_key"}
        self.use_case._validate_credentials(self.agent, credentials)

    def test_validate_credentials_missing_required(self):
        credentials = {}
        with self.assertRaises(ValidationError) as ctx:
            self.use_case._validate_credentials(self.agent, credentials)
        self.assertIn("Credential api_key is required", str(ctx.exception))

    def test_validate_credentials_multiple_missing(self):
        agent_with_multiple_creds = Agent.objects.create(
            name="Multi Cred Agent",
            lambda_arn="arn:aws:lambda:fake",
            project=self.project,
            credentials={
                "api_key": {"label": "API Key", "is_confidential": True},
                "secret_key": {"label": "Secret Key", "is_confidential": True},
            },
        )
        credentials = {"api_key": "test_key"}  # Missing secret_key
        with self.assertRaises(ValidationError) as ctx:
            self.use_case._validate_credentials(agent_with_multiple_creds, credentials)
        self.assertIn("Credential secret_key is required", str(ctx.exception))

    def test_create_credentials_success(self):
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )
        credentials = {"api_key": "test_key_value"}

        self.use_case._create_credentials(integrated_agent, self.agent, credentials)

        credential = Credential.objects.get(
            key="api_key", integrated_agent=integrated_agent
        )
        self.assertEqual(credential.value, "test_key_value")
        self.assertEqual(credential.label, "API Key")
        self.assertEqual(credential.placeholder, "Enter API key")
        self.assertTrue(credential.is_confidential)

    def test_create_credentials_skip_unknown_keys(self):
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )
        credentials = {"api_key": "test_key_value", "unknown_key": "unknown_value"}

        self.use_case._create_credentials(integrated_agent, self.agent, credentials)

        self.assertEqual(
            Credential.objects.filter(integrated_agent=integrated_agent).count(), 1
        )
        self.assertTrue(
            Credential.objects.filter(
                key="api_key", integrated_agent=integrated_agent
            ).exists()
        )
        self.assertFalse(
            Credential.objects.filter(
                key="unknown_key", integrated_agent=integrated_agent
            ).exists()
        )

    def test_create_credentials_get_or_create(self):
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )
        credentials = {"api_key": "test_key_value"}

        self.use_case._create_credentials(integrated_agent, self.agent, credentials)
        self.use_case._create_credentials(integrated_agent, self.agent, credentials)

        self.assertEqual(
            Credential.objects.filter(
                key="api_key", integrated_agent=integrated_agent
            ).count(),
            1,
        )

    @patch("retail.agents.assign.usecases.assign_agent.CreateLibraryTemplateUseCase")
    def test_create_templates_success(self, mock_create_library_use_case):
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )

        pre_approved = MagicMock()
        pre_approved.is_valid = True
        pre_approved.metadata = {
            "name": "Test Template",
            "category": "greeting",
            "language": "en",
        }
        pre_approved.start_condition = "test_condition"
        pre_approved.slug = "test-template"

        pre_approveds = MagicMock()
        pre_approveds.exclude.return_value = [pre_approved]

        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_version.template_name = "Test Template"
        mock_version.uuid = uuid.uuid4()

        mock_use_case_instance = mock_create_library_use_case.return_value
        mock_use_case_instance.execute.return_value = (mock_template, mock_version)

        self.use_case._create_templates(
            integrated_agent=integrated_agent,
            pre_approveds=pre_approveds,
            project_uuid=self.project.uuid,
            app_uuid=uuid.uuid4(),
            ignore_templates=[],
        )

        mock_use_case_instance.execute.assert_called_once()
        mock_use_case_instance.notify_integrations.assert_called_once()

    def test_get_ignore_templates(self):
        template1 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template1",
        )
        template2 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template2",
        )
        template3 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template3",
        )

        include_templates = [str(template1.uuid)]
        result = self.use_case._get_ignore_templates(self.agent, include_templates)

        self.assertIsInstance(result, list)
        self.assertIn(template2.uuid, result)
        self.assertIn(template3.uuid, result)
        self.assertNotIn(template1.uuid, result)

    def test_get_ignore_templates_slugs(self):
        template1 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template1",
        )
        template2 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template2",
        )

        ignore_templates = [template1.uuid, template2.uuid]
        result = self.use_case._get_ignore_templates_slugs(ignore_templates)

        self.assertIsInstance(result, list)
        self.assertIn("template1", result)
        self.assertIn("template2", result)

    @patch("retail.agents.assign.usecases.assign_agent.CreateLibraryTemplateUseCase")
    def test_execute_integration(self, mock_create_library_use_case):
        mock_use_case_instance = mock_create_library_use_case.return_value
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_use_case_instance.execute.return_value = (mock_template, mock_version)

        integrated_agent = self.use_case.execute(
            self.agent,
            self.project.uuid,
            uuid.uuid4(),
            uuid.uuid4(),
            {"api_key": "test_key"},
            [],
        )

        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertEqual(integrated_agent.agent, self.agent)
        self.assertEqual(integrated_agent.project, self.project)
        self.assertTrue(integrated_agent.is_active)

    def test_execute_project_not_found(self):
        random_uuid = uuid.uuid4()
        with self.assertRaises(NotFound):
            self.use_case.execute(
                self.agent,
                random_uuid,
                uuid.uuid4(),
                uuid.uuid4(),
                {"api_key": "test_key"},
                [],
            )

    def test_execute_validation_error_missing_credentials(self):
        with self.assertRaises(ValidationError):
            self.use_case.execute(
                self.agent,
                self.project.uuid,
                uuid.uuid4(),
                uuid.uuid4(),
                {},
                [],
            )

    def test_execute_already_assigned_agent(self):
        self.use_case.execute(
            self.agent,
            self.project.uuid,
            uuid.uuid4(),
            uuid.uuid4(),
            {"api_key": "test_key"},
            [],
        )

        with self.assertRaises(ValidationError) as ctx:
            self.use_case.execute(
                self.agent,
                self.project.uuid,
                uuid.uuid4(),
                uuid.uuid4(),
                {"api_key": "test_key"},
                [],
            )
        self.assertIn(
            "This agent is already assigned in this project", str(ctx.exception)
        )

    @patch("retail.agents.assign.usecases.assign_agent.CreateLibraryTemplateUseCase")
    def test_execute_with_include_templates(self, mock_create_library_use_case):
        mock_use_case_instance = mock_create_library_use_case.return_value
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_use_case_instance.execute.return_value = (mock_template, mock_version)

        template1 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="template1",
        )

        include_templates = [str(template1.uuid)]

        integrated_agent = self.use_case.execute(
            self.agent,
            self.project.uuid,
            uuid.uuid4(),
            uuid.uuid4(),
            {"api_key": "test_key"},
            include_templates,
        )

        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertNotIn(template1.slug, integrated_agent.ignore_templates)
