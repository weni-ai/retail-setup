import json

import copy

from unittest.mock import patch, Mock

from uuid import uuid4

from django.test import TestCase

from rest_framework.exceptions import NotFound

from retail.templates.usecases.create_custom_template import (
    CreateCustomTemplateUseCase,
    CreateCustomTemplateData,
    LambdaResponseStatusCode,
)
from retail.templates.models import Template, Version
from retail.templates.exceptions import (
    CodeGeneratorBadRequest,
    CodeGeneratorUnprocessableEntity,
    CodeGeneratorInternalServerError,
    CustomTemplateAlreadyExists,
)
from retail.projects.models import Project
from retail.agents.models import Agent, IntegratedAgent


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

        self.mock_lambda_service = Mock()
        self.mock_template_adapter = Mock()

        self.use_case = CreateCustomTemplateUseCase(
            lambda_service=self.mock_lambda_service,
            template_adapter=self.mock_template_adapter,
        )

        self.valid_payload: CreateCustomTemplateData = {
            "template_translation": {
                "template_header": "Test Header",
                "template_body": "Test Body",
                "template_footer": "Test Footer",
                "template_button": [{"type": "URL", "text": "Click here"}],
            },
            "template_name": "test_template",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project_uuid),
            "integrated_agent_uuid": self.integrated_agent_uuid,
            "parameters": [
                {
                    "name": "variables",
                    "value": '[{"definition": "test", "fallback": "default"}]',
                },
                {"name": "start_condition", "value": "test condition"},
                {"name": "examples", "value": '[{"input": "example"}]'},
                {"name": "template_content", "value": "some template text"},
            ],
            "display_name": "Test Display Name",
        }

        self.successful_lambda_response = {
            "statusCode": LambdaResponseStatusCode.OK,
            "body": {"generated_code": "def test_rule(): return True"},
        }

        self.adapted_translation = {
            "header": {"header_type": "TEXT", "text": "Test Header"},
            "body": {"type": "BODY", "text": "Test Body"},
            "footer": {"type": "FOOTER", "text": "Test Footer"},
            "buttons": [{"type": "URL", "text": "Click here"}],
        }

    def _setup_mocks_for_successful_execution(self):
        mock_payload = Mock()
        mock_payload.read.return_value = json.dumps(
            self.successful_lambda_response
        ).encode()

        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}
        self.mock_template_adapter.adapt.return_value = self.adapted_translation

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

        expected_metadata = {
            "body": "Test Body",
            "header": "Test Header",
            "footer": "Test Footer",
            "buttons": [{"type": "URL", "text": "Click here"}],
            "category": "test",
        }
        self.assertEqual(result.metadata, expected_metadata)

        version = Version.objects.get(template=result)
        self.assertIsNotNone(version)

        self.mock_lambda_service.invoke.assert_called_once()
        call_args = self.mock_lambda_service.invoke.call_args
        self.assertEqual(
            call_args[1]["payload"]["parameters"], self.valid_payload["parameters"]
        )

        self.mock_template_adapter.adapt.assert_called_once()

        mock_task_create_template.delay.assert_called_once()

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_buttons_modification_in_notify_integrations(
        self, mock_task_create_template
    ):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        translation_with_buttons = copy.deepcopy(self.adapted_translation)
        translation_with_buttons["buttons"] = [{"type": "URL", "text": "Test Button"}]
        self.mock_template_adapter.adapt.return_value = translation_with_buttons

        result = self.use_case.execute(self.valid_payload)

        self.assertIn("buttons", result.metadata)
        self.assertEqual(result.metadata["buttons"][0]["type"], "URL")

        mock_task_create_template.delay.assert_called_once()
        call_args = mock_task_create_template.delay.call_args.kwargs
        self.assertIn("template_translation", call_args)

        notify_translation = call_args["template_translation"]
        if "buttons" in notify_translation:
            self.assertEqual(notify_translation["buttons"][0]["button_type"], "URL")
            self.assertNotIn("type", notify_translation["buttons"][0])

    def test_execute_integrated_agent_not_found(self):
        self._setup_mocks_for_successful_execution()

        invalid_payload = copy.deepcopy(self.valid_payload)
        invalid_payload["integrated_agent_uuid"] = uuid4()

        with self.assertRaises(NotFound) as context:
            self.use_case.execute(invalid_payload)

        self.assertIn("Assigned agent not found", str(context.exception))

    def test_execute_integrated_agent_inactive(self):
        self._setup_mocks_for_successful_execution()

        self.integrated_agent.is_active = False
        self.integrated_agent.save()

        with self.assertRaises(NotFound) as context:
            self.use_case.execute(self.valid_payload)

        self.assertIn("Assigned agent not found", str(context.exception))

    def test_execute_lambda_bad_request_error(self):
        mock_payload = Mock()
        error_response = {
            "statusCode": LambdaResponseStatusCode.BAD_REQUEST,
            "body": {"error": "Invalid parameters"},
        }
        mock_payload.read.return_value = json.dumps(error_response).encode()
        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}

        with self.assertRaises(CodeGeneratorBadRequest) as context:
            self.use_case.execute(self.valid_payload)

        self.assertEqual(context.exception.detail, {"error": "Invalid parameters"})

    def test_execute_lambda_unprocessable_entity_error(self):
        mock_payload = Mock()
        error_response = {
            "statusCode": LambdaResponseStatusCode.UNPROCESSABLE_ENTITY,
            "body": {"error": "Cannot process request"},
        }
        mock_payload.read.return_value = json.dumps(error_response).encode()
        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}

        with self.assertRaises(CodeGeneratorUnprocessableEntity) as context:
            self.use_case.execute(self.valid_payload)

        self.assertEqual(context.exception.detail, {"error": "Cannot process request"})

    def test_execute_lambda_unknown_error(self):
        mock_payload = Mock()
        error_response = {"statusCode": 500, "body": {"error": "Internal server error"}}
        mock_payload.read.return_value = json.dumps(error_response).encode()
        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}

        with self.assertRaises(CodeGeneratorInternalServerError) as context:
            self.use_case.execute(self.valid_payload)

        detail = context.exception.detail
        self.assertEqual(str(detail["message"]), "Unknown error from lambda.")
        self.assertEqual(str(detail["error"]["statusCode"]), "500")
        self.assertEqual(str(detail["error"]["body"]["error"]), "Internal server error")

    def test_execute_lambda_no_status_code(self):
        mock_payload = Mock()
        error_response = {"body": {"error": "No status code"}}
        mock_payload.read.return_value = json.dumps(error_response).encode()
        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}

        with self.assertRaises(CodeGeneratorInternalServerError) as context:
            self.use_case.execute(self.valid_payload)

        detail = context.exception.detail
        self.assertEqual(str(detail["message"]), "Unknown error from lambda.")
        self.assertEqual(str(detail["error"]["body"]["error"]), "No status code")

    def test_get_start_condition_from_parameters(self):
        self._setup_mocks_for_successful_execution()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["parameters"][1]["value"] = "custom start condition"

        with patch(
            "retail.templates.usecases.create_custom_template.task_create_template"
        ) as mock_task:
            mock_task.delay.return_value = Mock()
            result = self.use_case.execute(modified_payload)

        self.assertEqual(result.start_condition, "custom start condition")

    def test_get_start_condition_not_found_in_parameters(self):
        self._setup_mocks_for_successful_execution()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["parameters"] = [
            param
            for param in modified_payload["parameters"]
            if param["name"] != "start_condition"
        ]

        with patch(
            "retail.templates.usecases.create_custom_template.task_create_template"
        ) as mock_task:
            mock_task.delay.return_value = Mock()
            result = self.use_case.execute(modified_payload)

        self.assertIsNone(result.start_condition)

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_creates_template_and_version_relationship(
        self, mock_task_create_template
    ):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        result = self.use_case.execute(self.valid_payload)

        self.assertTrue(Template.objects.filter(uuid=result.uuid).exists())

        version = Version.objects.get(template=result)
        self.assertEqual(version.template, result)
        self.assertEqual(version.project, self.project)

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_invoke_code_generator_with_correct_payload(
        self, mock_task_create_template
    ):
        mock_payload = Mock()
        mock_payload.read.return_value = json.dumps(
            self.successful_lambda_response
        ).encode()
        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}
        self.mock_template_adapter.adapt.return_value = self.adapted_translation
        mock_task_create_template.delay.return_value = Mock()

        self.use_case.execute(self.valid_payload)

        self.mock_lambda_service.invoke.assert_called_once()
        call_args = self.mock_lambda_service.invoke.call_args

        expected_payload = {"parameters": self.valid_payload["parameters"]}
        self.assertEqual(call_args[1]["payload"], expected_payload)

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_adapt_translation_called_with_correct_data(
        self, mock_task_create_template
    ):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        self.use_case.execute(self.valid_payload)

        self.mock_template_adapter.adapt.assert_called_once()
        call_args = self.mock_template_adapter.adapt.call_args[0][0]

        expected_structure = {
            "header": self.valid_payload["template_translation"]["template_header"],
            "body": self.valid_payload["template_translation"]["template_body"],
            "footer": self.valid_payload["template_translation"]["template_footer"],
            "buttons": self.valid_payload["template_translation"]["template_button"],
            "category": "test",
        }
        self.assertEqual(call_args, expected_structure)

    def test_execute_custom_template_already_exists(self):
        self._setup_mocks_for_successful_execution()

        Template.objects.create(
            uuid=uuid4(),
            name="existing_template",
            display_name="Test Display Name",
            integrated_agent=self.integrated_agent,
            rule_code="def existing_rule(): return True",
            metadata={"test": "data"},
        )

        with self.assertRaises(CustomTemplateAlreadyExists) as context:
            self.use_case.execute(self.valid_payload)

        self.assertIn(
            "Custom template with this display name already exists",
            str(context.exception),
        )

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_empty_parameters_list(self, mock_task_create_template):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["parameters"] = []

        result = self.use_case.execute(modified_payload)

        self.assertIsInstance(result, Template)
        self.assertIsNone(result.start_condition)

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_missing_translation_fields(self, mock_task_create_template):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["template_translation"] = {
            "template_body": "Only body content",
        }

        self.mock_template_adapter.adapt.return_value = {
            "header": None,
            "body": {"type": "BODY", "text": "Only body content"},
            "footer": None,
            "buttons": None,
        }

        result = self.use_case.execute(modified_payload)

        self.assertIsInstance(result, Template)
        self.mock_template_adapter.adapt.assert_called_once()
        call_args = self.mock_template_adapter.adapt.call_args[0][0]
        self.assertEqual(call_args["body"], "Only body content")
        self.assertIsNone(call_args["header"])
        self.assertIsNone(call_args["footer"])
        self.assertIsNone(call_args["buttons"])

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_with_none_generated_code(self, mock_task_create_template):
        mock_payload = Mock()
        response_with_none_code = {
            "statusCode": LambdaResponseStatusCode.OK,
            "body": {"generated_code": None},
        }
        mock_payload.read.return_value = json.dumps(response_with_none_code).encode()
        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}
        self.mock_template_adapter.adapt.return_value = self.adapted_translation
        mock_task_create_template.delay.return_value = Mock()

        result = self.use_case.execute(self.valid_payload)

        self.assertIsInstance(result, Template)
        self.assertIsNone(result.rule_code)

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_template_name_generation_from_display_name(
        self, mock_task_create_template
    ):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["display_name"] = "My Custom Template Name"

        result = self.use_case.execute(modified_payload)

        self.assertIsInstance(result, Template)
        version = Version.objects.get(template=result)
        self.assertIn("my_custom_template_name", version.template_name)

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_notify_integrations_without_buttons(
        self, mock_task_create_template
    ):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        translation_without_buttons = copy.deepcopy(self.adapted_translation)
        translation_without_buttons["buttons"] = None
        self.mock_template_adapter.adapt.return_value = translation_without_buttons

        result = self.use_case.execute(self.valid_payload)

        self.assertIsInstance(result, Template)
        self.assertIn("buttons", result.metadata)
        self.assertIsNone(result.metadata["buttons"])

        mock_task_create_template.delay.assert_called_once()
        call_args = mock_task_create_template.delay.call_args.kwargs
        notify_translation = call_args["template_translation"]
        self.assertIn("buttons", notify_translation)
        self.assertIsNone(notify_translation["buttons"])

    @patch("retail.templates.usecases.create_custom_template.task_create_template")
    def test_execute_multiple_parameters_with_same_name(
        self, mock_task_create_template
    ):
        self._setup_mocks_for_successful_execution()
        mock_task_create_template.delay.return_value = Mock()

        modified_payload = copy.deepcopy(self.valid_payload)
        modified_payload["parameters"] = [
            {"name": "start_condition", "value": "first condition"},
            {"name": "start_condition", "value": "second condition"},
            {"name": "other_param", "value": "other value"},
        ]

        result = self.use_case.execute(modified_payload)

        self.assertIsInstance(result, Template)
        self.assertEqual(result.start_condition, "first condition")

    def test_execute_lambda_service_exception(self):
        self.mock_lambda_service.invoke.side_effect = Exception("Lambda service error")

        with self.assertRaises(Exception) as context:
            self.use_case.execute(self.valid_payload)

        self.assertEqual(str(context.exception), "Lambda service error")

    def test_execute_json_decode_error_in_lambda_response(self):
        mock_payload = Mock()
        mock_payload.read.return_value = b"invalid json response"
        self.mock_lambda_service.invoke.return_value = {"Payload": mock_payload}

        with self.assertRaises(json.JSONDecodeError):
            self.use_case.execute(self.valid_payload)
