from unittest.mock import patch, MagicMock
from uuid import uuid4
from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.templates.usecases.update_template_body import (
    UpdateTemplateContentUseCase,
    UpdateTemplateContentData,
)


class TestUpdateTemplateContentUseCase(TestCase):
    def setUp(self):
        self.mock_service = MagicMock()
        self.mock_template_adapter = MagicMock()
        self.use_case = UpdateTemplateContentUseCase(
            service=self.mock_service,
            template_adapter=self.mock_template_adapter,
        )

        self.template_uuid = str(uuid4())
        self.app_uuid = "app-123"
        self.project_uuid = "project-456"
        self.version_uuid = uuid4()

        self.payload = UpdateTemplateContentData(
            template_uuid=self.template_uuid,
            template_body="Updated body",
            template_header="Updated header",
            template_footer="Updated footer",
            template_button=[{"type": "QUICK_REPLY", "text": "Button 1"}],
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
        )

    @patch("retail.templates.usecases.update_template_body.Template")
    def test_get_template_success(self, mock_template_model):
        mock_template = MagicMock()
        mock_template_model.objects.get.return_value = mock_template

        result = self.use_case.get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(uuid=self.template_uuid)
        self.assertEqual(result, mock_template)

    @patch("retail.templates.usecases.update_template_body.Template")
    def test_get_template_not_found(self, mock_template_model):
        mock_template_model.DoesNotExist = Exception
        mock_template_model.objects.get.side_effect = mock_template_model.DoesNotExist()

        with self.assertRaises(NotFound) as context:
            self.use_case.get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(uuid=self.template_uuid)
        self.assertEqual(
            str(context.exception), f"Template not found: {self.template_uuid}"
        )

    @patch("retail.templates.usecases.update_template_body.task_create_template")
    def test_notify_integrations_success(self, mock_task):
        version_name = "Test Template"
        translation_payload = {"body": {"type": "BODY", "text": "Test body"}}
        category = "marketing"

        self.use_case._notify_integrations(
            version_name=version_name,
            version_uuid=self.version_uuid,
            translation_payload=translation_payload,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=category,
        )

        mock_task.delay.assert_called_once_with(
            template_name=version_name,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=category,
            version_uuid=str(self.version_uuid),
            template_translation=translation_payload,
        )

    def test_notify_integrations_missing_data(self):
        with self.assertRaises(ValueError) as context:
            self.use_case._notify_integrations(
                version_name="",
                version_uuid=self.version_uuid,
                translation_payload={},
                app_uuid=self.app_uuid,
                project_uuid=self.project_uuid,
                category="marketing",
            )

        self.assertEqual(
            str(context.exception), "Missing required data to notify integrations"
        )

    @patch.object(UpdateTemplateContentUseCase, "_create_version")
    @patch.object(UpdateTemplateContentUseCase, "_notify_integrations")
    def test_execute_success(self, mock_notify, mock_create_version):
        mock_template = MagicMock()
        mock_template.metadata = {
            "category": "marketing",
            "body": "Original body",
            "header": "Original header",
            "footer": "Original footer",
            "buttons": [{"type": "URL", "text": "Original Button"}],
        }

        mock_version = MagicMock()
        mock_version.template_name = "Test Template"
        mock_version.uuid = self.version_uuid
        mock_create_version.return_value = mock_version

        self.mock_template_adapter.adapt.return_value = {
            "body": {"type": "BODY", "text": "Updated body"},
            "buttons": [{"text": "Button 1", "type": "URL"}],
        }

        result = self.use_case.execute(self.payload, mock_template)

        expected_metadata = {
            "category": "marketing",
            "body": "Updated body",
            "header": "Updated header",
            "footer": "Updated footer",
            "buttons": [{"text": "Button 1", "button_type": "URL"}],
        }

        self.mock_template_adapter.adapt.assert_called_once_with(expected_metadata)
        mock_template.save.assert_called_once_with(update_fields=["metadata"])

        mock_create_version.assert_called_once_with(
            template=mock_template,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
        )

        mock_notify.assert_called_once_with(
            version_name="Test Template",
            version_uuid=self.version_uuid,
            translation_payload={
                "body": {"type": "BODY", "text": "Updated body"},
                "buttons": [{"text": "Button 1", "button_type": "URL"}],
            },
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category="marketing",
        )

        self.assertEqual(result, mock_template)

    def test_execute_missing_metadata(self):
        mock_template = MagicMock()
        mock_template.metadata = None

        with self.assertRaises(ValueError) as context:
            self.use_case.execute(self.payload, mock_template)

        self.assertEqual(str(context.exception), "Template metadata is missing")

    def test_execute_missing_category(self):
        mock_template = MagicMock()
        mock_template.metadata = {"body": "Test body"}

        with self.assertRaises(ValueError) as context:
            self.use_case.execute(self.payload, mock_template)

        self.assertEqual(
            str(context.exception), "Missing category in template metadata"
        )

    @patch.object(UpdateTemplateContentUseCase, "_create_version")
    @patch.object(UpdateTemplateContentUseCase, "_notify_integrations")
    def test_execute_with_button_type_transformation(
        self, mock_notify, mock_create_version
    ):
        mock_template = MagicMock()
        mock_template.metadata = {
            "category": "marketing",
            "body": "Original body",
            "buttons": [{"type": "QUICK_REPLY", "text": "Button 1"}],
        }

        mock_version = MagicMock()
        mock_version.template_name = "Test Template"
        mock_version.uuid = self.version_uuid
        mock_create_version.return_value = mock_version

        self.mock_template_adapter.adapt.return_value = {
            "buttons": [{"type": "QUICK_REPLY", "text": "Button 1"}],
        }

        self.use_case.execute(self.payload, mock_template)

    @patch.object(UpdateTemplateContentUseCase, "_create_version")
    @patch.object(UpdateTemplateContentUseCase, "_notify_integrations")
    def test_execute_uses_existing_values_when_not_provided(
        self, mock_notify, mock_create_version
    ):
        mock_template = MagicMock()
        mock_template.metadata = {
            "category": "marketing",
            "body": "Original body",
            "header": "Original header",
            "footer": "Original footer",
            "buttons": [{"type": "QUICK_REPLY", "text": "Original Button"}],
        }

        mock_version = MagicMock()
        mock_version.template_name = "Test Template"
        mock_version.uuid = self.version_uuid
        mock_create_version.return_value = mock_version

        self.mock_template_adapter.adapt.return_value = {"buttons": []}

        partial_payload = UpdateTemplateContentData(
            template_uuid=self.template_uuid,
            template_body="Updated body only",
            template_header="",
            template_footer="",
            template_button=[],
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
        )

        self.use_case.execute(partial_payload, mock_template)

        expected_metadata = {
            "category": "marketing",
            "body": "Updated body only",
            "header": "",
            "footer": "",
            "buttons": [],
        }

        self.mock_template_adapter.adapt.assert_called_once_with(expected_metadata)

    def test_init_with_custom_dependencies(self):
        mock_service = MagicMock()
        mock_adapter = MagicMock()

        use_case = UpdateTemplateContentUseCase(
            service=mock_service,
            template_adapter=mock_adapter,
        )

        self.assertEqual(use_case.service, mock_service)
        self.assertEqual(use_case.template_adapter, mock_adapter)

    def test_init_with_default_dependencies(self):
        use_case = UpdateTemplateContentUseCase()

        self.assertIsNotNone(use_case.service)
        self.assertIsNotNone(use_case.template_adapter)
