import copy

from unittest.mock import patch, Mock

from uuid import uuid4

from django.test import TestCase, override_settings

from rest_framework.exceptions import NotFound

from retail.templates.usecases.create_custom_template import (
    CreateCustomTemplateUseCase,
    CreateCustomTemplateData,
)
from retail.templates.models import Template, Version
from retail.templates.exceptions import CustomTemplateAlreadyExists
from retail.projects.models import Project
from retail.agents.models import Agent, IntegratedAgent
from retail.services.rule_generator import (
    RuleGenerator,
    RuleGeneratorBadRequest,
    RuleGeneratorUnprocessableEntity,
    RuleGeneratorInternalServerError,
)


@override_settings(
    CELERY_TASK_ALWAYS_EAGER=True,
    CELERY_BROKER_URL="memory://",
    CELERY_RESULT_BACKEND="cache+memory://",
    REDIS_URL="redis://localhost:6379/1",
)
class CreateCustomTemplateUseCaseTest(TestCase):
    def setUp(self):
        self.project_uuid = uuid4()
        self.agent_uuid = uuid4()
        self.integrated_agent_uuid = uuid4()

        self.project = Project.objects.create(
            name="Test Project", uuid=self.project_uuid
        )

        self.agent = Agent.objects.create(
            uuid=self.agent_uuid,
            name="Test Agent",
            slug="test-agent",
            description="Test Description",
            project=self.project,
        )

        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=self.integrated_agent_uuid,
            agent=self.agent,
            project=self.project,
            is_active=True,
        )

        self.mock_rule_generator = Mock(spec=RuleGenerator)
        self.mock_template_adapter = Mock()
        self.mock_metadata_handler = Mock()

        self.use_case = CreateCustomTemplateUseCase(
            rule_generator=self.mock_rule_generator,
            template_adapter=self.mock_template_adapter,
            template_metadata_handler=self.mock_metadata_handler,
        )

        self.valid_payload: CreateCustomTemplateData = {
            "template_translation": {
                "en": {"text": "Hello, {{name}}!"},
                "pt": {"text": "Olá, {{name}}!"},
            },
            "category": "UTILITY",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project_uuid),
            "integrated_agent_uuid": self.integrated_agent_uuid,
            "display_name": "Test Display Name",
            "parameters": [
                {"name": "start_condition", "value": "test condition"},
                {"name": "variables", "value": [{"name": "name", "type": "text"}]},
            ],
        }

    def _setup_mocks_for_successful_execution(self):
        self.mock_rule_generator.generate_code.return_value = (
            "def test_rule(): return True"
        )

        self.mock_metadata_handler.build_metadata.return_value = {
            "body": "Hello, {{name}}!",
            "category": "UTILITY",
        }

        self.mock_template_adapter.adapt.return_value = {
            "en": {"text": "Hello, {{name}}!"},
            "pt": {"text": "Olá, {{name}}!"},
        }

        self.mock_metadata_handler.post_process_translation.side_effect = (
            lambda metadata, translation: metadata
        )

        self.mock_metadata_handler.extract_start_condition.return_value = (
            "test condition"
        )
        self.mock_metadata_handler.extract_variables.return_value = [
            {"name": "name", "type": "text"}
        ]

        return self.mock_metadata_handler, self.mock_template_adapter

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_successful_creation(self, mock_task_create_template):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        result = self.use_case.execute(self.valid_payload)

        self.assertIsInstance(result, Template)
        self.assertEqual(result.display_name, "Test Display Name")
        self.assertEqual(result.start_condition, "test condition")
        self.assertEqual(result.rule_code, "def test_rule(): return True")
        self.assertEqual(result.integrated_agent, self.integrated_agent)

        expected_metadata = self.mock_metadata_handler.build_metadata.return_value
        self.assertEqual(result.metadata, expected_metadata)

        version = Version.objects.get(template=result)
        self.assertIsNotNone(version)

        self.mock_rule_generator.generate_code.assert_called_once_with(
            self.valid_payload["parameters"], self.integrated_agent
        )
        self.mock_template_adapter.adapt.assert_called_once()
        self.mock_metadata_handler.build_metadata.assert_called_once_with(
            self.valid_payload["template_translation"], self.valid_payload["category"]
        )
        self.mock_metadata_handler.post_process_translation.assert_called_once()
        self.mock_metadata_handler.extract_start_condition.assert_called_once()
        mock_task_create_template.delay.assert_called_once()

    def test_execute_template_already_exists(self):
        self._setup_mocks_for_successful_execution()

        Template.objects.create(
            name="existing_template",
            display_name="Test Display Name",
            integrated_agent=self.integrated_agent,
        )

        with self.assertRaises(CustomTemplateAlreadyExists) as context:
            self.use_case.execute(self.valid_payload)

        self.assertIn(
            "Custom template with this display name already exists",
            str(context.exception),
        )

    def test_execute_integrated_agent_not_found(self):
        invalid_payload = copy.deepcopy(self.valid_payload)
        invalid_payload["integrated_agent_uuid"] = uuid4()

        with self.assertRaises(NotFound) as context:
            self.use_case.execute(invalid_payload)

        self.assertIn("Assigned agent not found", str(context.exception))

    def test_execute_integrated_agent_inactive(self):
        self.integrated_agent.is_active = False
        self.integrated_agent.save()

        with self.assertRaises(NotFound) as context:
            self.use_case.execute(self.valid_payload)

        self.assertIn("Assigned agent not found", str(context.exception))

    def test_execute_rule_generator_bad_request_error(self):
        self.mock_rule_generator.generate_code.side_effect = RuleGeneratorBadRequest(
            detail={"error": "Invalid parameters"}
        )

        with self.assertRaises(RuleGeneratorBadRequest) as context:
            self.use_case.execute(self.valid_payload)

        self.assertEqual(context.exception.detail, {"error": "Invalid parameters"})

    def test_execute_rule_generator_unprocessable_entity_error(self):
        self.mock_rule_generator.generate_code.side_effect = (
            RuleGeneratorUnprocessableEntity(detail={"error": "Cannot process request"})
        )

        with self.assertRaises(RuleGeneratorUnprocessableEntity) as context:
            self.use_case.execute(self.valid_payload)

        self.assertEqual(context.exception.detail, {"error": "Cannot process request"})

    def test_execute_rule_generator_internal_server_error(self):
        self.mock_rule_generator.generate_code.side_effect = (
            RuleGeneratorInternalServerError(
                detail={
                    "message": "Unknown error from lambda.",
                    "error": {"statusCode": 500},
                }
            )
        )

        with self.assertRaises(RuleGeneratorInternalServerError) as context:
            self.use_case.execute(self.valid_payload)

        detail = context.exception.detail
        self.assertEqual(detail["message"], "Unknown error from lambda.")
        self.assertIn("statusCode", detail["error"])
        self.assertTrue(str(detail["error"]["statusCode"]) == "500")

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_get_start_condition_from_parameters(self, mock_task):
        """Testa extração de start_condition dos parâmetros."""
        self._setup_mocks_for_successful_execution()
        # Mock do task para evitar conexão Redis
        mock_task.delay.return_value = Mock()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["parameters"] = [
            {"name": "start_condition", "value": "test condition"},
            {"name": "other_param", "value": "other_value"},
        ]

        result = self.use_case.execute(modified_payload)

        self.assertIsInstance(result, Template)
        # Verificar se o start_condition foi extraído corretamente
        result.refresh_from_db()
        self.assertEqual(result.start_condition, "test condition")

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_empty_variables_list(self, mock_task):
        self._setup_mocks_for_successful_execution()
        self.mock_metadata_handler.extract_variables.return_value = []
        mock_task.delay.return_value = Mock()

        result = self.use_case.execute(self.valid_payload)

        self.assertEqual(result.variables, [])

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_null_variables(self, mock_task):
        self._setup_mocks_for_successful_execution()
        self.mock_metadata_handler.extract_variables.return_value = None
        mock_task.delay.return_value = Mock()

        result = self.use_case.execute(self.valid_payload)

        self.assertEqual(result.variables, [])

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_null_start_condition(self, mock_task):
        self._setup_mocks_for_successful_execution()
        self.mock_metadata_handler.extract_start_condition.return_value = None
        mock_task.delay.return_value = Mock()

        result = self.use_case.execute(self.valid_payload)

        self.assertIsNone(result.start_condition)

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_template_name_generation(self, mock_task):
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        payload = copy.deepcopy(self.valid_payload)
        payload["display_name"] = "My Custom Template"

        with patch.object(self.use_case, "build_template_and_version") as mock_build:
            mock_template = Mock()
            mock_version = Mock()
            mock_build.return_value = (mock_template, mock_version)

            self.use_case.execute(payload)

            call_args = mock_build.call_args[0][0]
            self.assertEqual(call_args["template_name"], "my_custom_template")

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_notify_integrations_with_buttons(self, mock_task):
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        self.mock_template_adapter.adapt.return_value = {
            "buttons": [
                {"type": "QUICK_REPLY", "text": "Quick Reply"},
                {"type": "URL", "text": "URL Button"},
            ]
        }

        self.use_case.execute(self.valid_payload)

        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        template_translation = call_kwargs["template_translation"]

        self.assertEqual(
            template_translation["buttons"][0]["button_type"], "QUICK_REPLY"
        )
        self.assertEqual(template_translation["buttons"][1]["button_type"], "URL")

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_notify_integrations_with_image_header(self, mock_task):
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        self.mock_template_adapter.adapt.return_value = {
            "header": {"type": "IMAGE", "text": "base64_image_data"}
        }

        self.use_case.execute(self.valid_payload)

        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        template_translation = call_kwargs["template_translation"]

        self.assertEqual(template_translation["header"]["example"], "base64_image_data")
        self.assertNotIn("text", template_translation["header"])

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_notify_integrations_with_text_header(self, mock_task):
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        self.mock_template_adapter.adapt.return_value = {
            "header": {"type": "TEXT", "text": "Text header"}
        }

        self.use_case.execute(self.valid_payload)

        mock_task.delay.assert_called_once()
        call_kwargs = mock_task.delay.call_args.kwargs
        template_translation = call_kwargs["template_translation"]

        self.assertEqual(template_translation["header"]["text"], "Text header")
        self.assertNotIn("example", template_translation["header"])

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_notify_integrations_creates_copy_of_translation(self, mock_task):
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        original_translation = {
            "buttons": [{"type": "QUICK_REPLY", "text": "Reply"}],
            "header": {"type": "IMAGE", "text": "image_data"},
        }
        self.mock_template_adapter.adapt.return_value = original_translation

        self.use_case.execute(self.valid_payload)

        self.assertEqual(original_translation["buttons"][0]["type"], "QUICK_REPLY")
        self.assertEqual(original_translation["header"]["text"], "image_data")

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_multiple_parameters_with_same_name(self, mock_task):
        """Testa execução com múltiplos parâmetros com mesmo nome."""
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["parameters"] = [
            {"name": "start_condition", "value": "first condition"},
            {"name": "start_condition", "value": "second condition"},
            {"name": "other_param", "value": "other_value"},
        ]

        # Mock para garantir que o primeiro valor seja retornado
        self.mock_metadata_handler.extract_start_condition.return_value = (
            "first condition"
        )

        result = self.use_case.execute(modified_payload)

        self.assertIsInstance(result, Template)
        # Verificar se o primeiro start_condition foi usado
        self.assertEqual(result.start_condition, "first condition")

    def test_execute_rule_generator_exception(self):
        self.mock_rule_generator.generate_code.side_effect = Exception(
            "Rule generator error"
        )

        with self.assertRaises(Exception) as context:
            self.use_case.execute(self.valid_payload)

        self.assertEqual(str(context.exception), "Rule generator error")

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_update_template_sets_all_fields_correctly(self, mock_task):
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        with patch.object(self.use_case, "build_template_and_version") as mock_build:
            template = Template.objects.create(
                name="test_template", integrated_agent=self.integrated_agent
            )
            version = Mock()
            mock_build.return_value = (template, version)

            self.use_case.execute(self.valid_payload)

            template.refresh_from_db()
            self.assertEqual(template.integrated_agent, self.integrated_agent)
            self.assertIsNotNone(template.metadata)
            self.assertEqual(template.metadata["category"], "UTILITY")
            self.assertEqual(template.rule_code, "def test_rule(): return True")
            self.assertEqual(template.display_name, "Test Display Name")
            self.assertEqual(template.start_condition, "test condition")
            self.assertEqual(template.variables, [{"name": "name", "type": "text"}])

    def test_get_integrated_agent_success(self):
        result = self.use_case._get_integrated_agent(self.integrated_agent_uuid)
        self.assertEqual(result, self.integrated_agent)

    def test_get_integrated_agent_not_found(self):
        with self.assertRaises(NotFound) as context:
            self.use_case._get_integrated_agent(uuid4())

        self.assertIn("Assigned agent not found", str(context.exception))

    def test_get_integrated_agent_inactive(self):
        self.integrated_agent.is_active = False
        self.integrated_agent.save()

        with self.assertRaises(NotFound) as context:
            self.use_case._get_integrated_agent(self.integrated_agent_uuid)

        self.assertIn("Assigned agent not found", str(context.exception))

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_empty_parameters_list(self, mock_task):
        self._setup_mocks_for_successful_execution()
        mock_task.delay.return_value = Mock()

        payload = copy.deepcopy(self.valid_payload)
        payload["parameters"] = []

        result = self.use_case.execute(payload)
        self.assertIsInstance(result, Template)

    def test_init_with_default_dependencies(self):
        with patch(
            "retail.templates.usecases.create_custom_template.RuleGenerator"
        ) as mock_rg:
            with patch(
                "retail.templates.usecases.create_custom_template.TemplateTranslationAdapter"
            ) as mock_tta:
                with patch(
                    "retail.templates.usecases.create_custom_template.TemplateMetadataHandler"
                ) as mock_tmh:
                    CreateCustomTemplateUseCase()

                    mock_rg.assert_called_once()
                    mock_tta.assert_called_once()
                    mock_tmh.assert_called_once()

    def test_init_with_custom_dependencies(self):
        custom_rule_generator = Mock()
        custom_adapter = Mock()
        custom_handler = Mock()

        use_case = CreateCustomTemplateUseCase(
            rule_generator=custom_rule_generator,
            template_adapter=custom_adapter,
            template_metadata_handler=custom_handler,
        )

        self.assertEqual(use_case.rule_generator, custom_rule_generator)
        self.assertEqual(use_case.template_adapter, custom_adapter)
        self.assertEqual(use_case.metadata_handler, custom_handler)
