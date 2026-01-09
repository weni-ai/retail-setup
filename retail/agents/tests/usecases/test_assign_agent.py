import uuid

from unittest.mock import MagicMock, patch

from django.test import TestCase

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_integration.models import (
    IntegratedAgent,
    Credential,
)
from retail.agents.domains.agent_management.models import PreApprovedTemplate
from retail.agents.domains.agent_integration.usecases.assign import AssignAgentUseCase
from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
)
from retail.projects.models import Project


class AssignAgentUseCaseTest(TestCase):
    def setUp(self):
        self.mock_fetch_phone_code = MagicMock(spec=FetchCountryPhoneCodeUseCase)
        self.mock_fetch_phone_code.execute.return_value = "+55"
        self.use_case = AssignAgentUseCase(
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code
        )
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), name="Test Project", vtex_account="teststore"
        )
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

    def test_create_integrated_agent_sets_country_phone_code(self):
        self.mock_fetch_phone_code.execute.return_value = "+54"
        integrated_agent = self.use_case._create_integrated_agent(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            ignore_templates=[],
        )
        self.assertEqual(integrated_agent.config.get("country_phone_code"), "+54")
        self.mock_fetch_phone_code.execute.assert_called_once_with(self.project)

    def test_create_integrated_agent_no_phone_code_when_fetch_fails(self):
        self.mock_fetch_phone_code.execute.return_value = None
        integrated_agent = self.use_case._create_integrated_agent(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            ignore_templates=[],
        )
        self.assertNotIn("country_phone_code", integrated_agent.config)

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
        credentials = {"api_key": "test_key"}
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

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateLibraryTemplateUseCase"
    )
    def test_create_templates_success(self, mock_create_library_use_case):
        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        use_case = AssignAgentUseCase(
            integrations_service=mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )

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
        filtered_queryset = MagicMock()
        filtered_queryset.filter.side_effect = lambda is_valid: (
            [pre_approved] if is_valid else []
        )
        pre_approveds.exclude.return_value = filtered_queryset

        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_version.template_name = "Test Template"
        mock_version.uuid = uuid.uuid4()

        mock_use_case_instance = mock_create_library_use_case.return_value
        mock_use_case_instance.execute.return_value = (mock_template, mock_version)

        use_case._create_templates(
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

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateLibraryTemplateUseCase"
    )
    def test_execute_integration(self, mock_create_library_use_case):
        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        use_case = AssignAgentUseCase(
            integrations_service=mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )

        mock_use_case_instance = mock_create_library_use_case.return_value
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_use_case_instance.execute.return_value = (mock_template, mock_version)

        integrated_agent = use_case.execute(
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
        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        use_case = AssignAgentUseCase(
            integrations_service=mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )

        use_case.execute(
            self.agent,
            self.project.uuid,
            uuid.uuid4(),
            uuid.uuid4(),
            {"api_key": "test_key"},
            [],
        )

        with self.assertRaises(ValidationError) as ctx:
            use_case.execute(
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

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateLibraryTemplateUseCase"
    )
    def test_execute_with_include_templates(self, mock_create_library_use_case):
        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        use_case = AssignAgentUseCase(
            integrations_service=mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )

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

        integrated_agent = use_case.execute(
            self.agent,
            self.project.uuid,
            uuid.uuid4(),
            uuid.uuid4(),
            {"api_key": "test_key"},
            include_templates,
        )

        self.assertIsInstance(integrated_agent, IntegratedAgent)
        self.assertNotIn(template1.slug, integrated_agent.ignore_templates)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.TemplateBuilderMixin"
    )
    def test_create_invalid_templates_success(self, mock_template_builder):
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )

        invalid_template1 = MagicMock()
        invalid_template1.name = "template_invalid_1"
        invalid_template1.start_condition = "start_condition_1"
        invalid_template1.display_name = "Template Inválido 1"

        invalid_template2 = MagicMock()
        invalid_template2.name = "template_invalid_2"
        invalid_template2.start_condition = "start_condition_2"
        invalid_template2.display_name = "Template Inválido 2"

        invalid_pre_approveds = [invalid_template1, invalid_template2]

        mock_translations = {
            "template_invalid_1": {
                "header": "Header 1",
                "body": "Body 1",
                "footer": "Footer 1",
                "buttons": [],
                "category": "MARKETING",
                "language": "pt_BR",
            }
        }
        self.use_case.integrations_service.fetch_templates_from_user = MagicMock(
            return_value=mock_translations
        )

        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_template_builder.return_value.build_template_and_version.return_value = (
            mock_template,
            mock_version,
        )

        project_uuid = self.project.uuid
        app_uuid = uuid.uuid4()

        self.use_case._create_invalid_templates(
            integrated_agent, invalid_pre_approveds, project_uuid, app_uuid
        )

        self.use_case.integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid,
            str(project_uuid),
            ["template_invalid_1", "template_invalid_2"],
            self.agent.language,
        )

        mock_template_builder.return_value.build_template_and_version.assert_called_once()

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.TemplateBuilderMixin"
    )
    def test_create_invalid_templates_no_translations_found(
        self, mock_template_builder
    ):
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )

        invalid_template = MagicMock()
        invalid_template.name = "template_not_found"
        invalid_pre_approveds = [invalid_template]

        self.use_case.integrations_service.fetch_templates_from_user = MagicMock(
            return_value={}
        )

        project_uuid = self.project.uuid
        app_uuid = uuid.uuid4()

        self.use_case._create_invalid_templates(
            integrated_agent, invalid_pre_approveds, project_uuid, app_uuid
        )

        self.use_case.integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid, str(project_uuid), ["template_not_found"], self.agent.language
        )

        mock_template_builder.return_value.build_template_and_version.assert_not_called()

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateLibraryTemplateUseCase"
    )
    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.TemplateBuilderMixin"
    )
    def test_create_templates_with_valid_and_invalid(
        self, mock_template_builder, mock_create_library_use_case
    ):
        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )

        PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="valid-template",
            name="valid_template",
            display_name="Template Válido",
            is_valid=True,
            start_condition="start_valid",
            metadata={"category": "MARKETING"},
        )

        PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="invalid-template",
            name="invalid_template",
            display_name="Template Inválido",
            is_valid=False,
            start_condition="start_invalid",
            metadata={"category": "UTILITY"},
        )

        templates = self.agent.templates.all()

        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_version.template_name = "valid_template"
        mock_version.uuid = uuid.uuid4()

        mock_use_case_instance = mock_create_library_use_case.return_value
        mock_use_case_instance.execute.return_value = (mock_template, mock_version)

        mock_invalid_template = MagicMock()
        mock_invalid_version = MagicMock()
        mock_template_builder.return_value.build_template_and_version.return_value = (
            mock_invalid_template,
            mock_invalid_version,
        )

        self.use_case.integrations_service.fetch_templates_from_user = MagicMock(
            return_value={"invalid_template": {"header": "Test", "body": "Test"}}
        )

        project_uuid = self.project.uuid
        app_uuid = uuid.uuid4()

        self.use_case._create_templates(
            integrated_agent, templates, project_uuid, app_uuid, []
        )

        mock_use_case_instance.execute.assert_called_once()
        self.use_case.integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid, str(project_uuid), ["invalid_template"], self.agent.language
        )

    def test_create_templates_with_integrations_service_mock(self):
        mock_integrations_service = MagicMock()
        use_case_with_mock = AssignAgentUseCase(
            integrations_service=mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )

        integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid.uuid4(),
            is_active=True,
        )

        invalid_template = MagicMock()
        invalid_template.name = "test_template"

        mock_integrations_service.fetch_templates_from_user.return_value = {}

        use_case_with_mock._create_invalid_templates(
            integrated_agent, [invalid_template], self.project.uuid, uuid.uuid4()
        )

        mock_integrations_service.fetch_templates_from_user.assert_called_once()

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateLibraryTemplateUseCase"
    )
    def test_execute_integration_with_valid_and_invalid_templates(
        self, mock_create_library_use_case
    ):
        mock_integrations_service = MagicMock()
        use_case = AssignAgentUseCase(
            integrations_service=mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )

        valid_template = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="valid-template",
            name="valid_template",
            display_name="Template Válido",
            is_valid=True,
            start_condition="start_valid",
            metadata={"category": "MARKETING", "language": "pt_BR"},
        )

        invalid_template = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="invalid-template",
            name="invalid_template",
            display_name="Template Inválido",
            is_valid=False,
            start_condition="start_invalid",
            metadata={"category": "UTILITY"},
        )

        mock_use_case_instance = mock_create_library_use_case.return_value
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_version.template_name = "valid_template"
        mock_version.uuid = uuid.uuid4()
        mock_use_case_instance.execute.return_value = (mock_template, mock_version)

        mock_integrations_service.fetch_templates_from_user.return_value = {
            "invalid_template": {
                "header": "Header Inválido",
                "body": "Body Inválido",
                "footer": "Footer Inválido",
                "buttons": [],
                "category": "UTILITY",
                "language": "pt_BR",
            }
        }

        app_uuid = uuid.uuid4()
        channel_uuid = uuid.uuid4()
        credentials = {"api_key": "test_key"}
        include_templates = [
            str(valid_template.uuid),
            str(invalid_template.uuid),
        ]

        use_case.execute(
            agent=self.agent,
            project_uuid=self.project.uuid,
            app_uuid=app_uuid,
            channel_uuid=channel_uuid,
            credentials=credentials,
            include_templates=include_templates,
        )

        mock_use_case_instance.execute.assert_called_once()

        mock_integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid, str(self.project.uuid), ["invalid_template"], self.agent.language
        )

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.CreateLibraryTemplateUseCase"
    )
    def test_execute_integration_with_only_invalid_templates_no_translations(
        self, mock_create_library_use_case
    ):
        mock_integrations_service = MagicMock()
        use_case = AssignAgentUseCase(
            integrations_service=mock_integrations_service,
            fetch_country_phone_code_usecase=self.mock_fetch_phone_code,
        )

        invalid_template1 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="invalid-template-1",
            name="invalid_template_1",
            display_name="Template Inválido 1",
            is_valid=False,
            start_condition="start_invalid_1",
            metadata={"category": "UTILITY"},
        )

        invalid_template2 = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid.uuid4(),
            slug="invalid-template-2",
            name="invalid_template_2",
            display_name="Template Inválido 2",
            is_valid=False,
            start_condition="start_invalid_2",
            metadata={"category": "UTILITY"},
        )

        mock_integrations_service.fetch_templates_from_user.return_value = {}

        app_uuid = uuid.uuid4()
        channel_uuid = uuid.uuid4()
        credentials = {"api_key": "test_key"}
        include_templates = []

        integrated_agent = use_case.execute(
            agent=self.agent,
            project_uuid=self.project.uuid,
            app_uuid=app_uuid,
            channel_uuid=channel_uuid,
            credentials=credentials,
            include_templates=include_templates,
        )

        self.assertIsInstance(integrated_agent, IntegratedAgent)

        self.assertIn(invalid_template1.slug, integrated_agent.ignore_templates)
        self.assertIn(invalid_template2.slug, integrated_agent.ignore_templates)

        mock_integrations_service.fetch_templates_from_user.assert_called_once_with(
            app_uuid, str(self.project.uuid), [], self.agent.language
        )

        mock_create_library_use_case.return_value.execute.assert_not_called()
