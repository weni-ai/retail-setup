from unittest.mock import patch, MagicMock
from uuid import uuid4
from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.templates.usecases.update_library_template import (
    UpdateLibraryTemplateUseCase,
    UpdateLibraryTemplateData,
)


class TestUpdateLibraryTemplateUseCase(TestCase):
    def setUp(self):
        self.use_case = UpdateLibraryTemplateUseCase()
        self.template_uuid = str(uuid4())
        self.app_uuid = "app-123"
        self.project_uuid = "project-456"
        self.version_uuid = uuid4()

        self.payload = UpdateLibraryTemplateData(
            template_uuid=self.template_uuid,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            library_template_button_inputs=[
                {
                    "type": "URL",
                    "text": "Ver detalhes",
                    "url": {
                        "base_url": "https://example.com",
                        "url_suffix_example": "/product/123",
                    },
                }
            ],
        )

    @patch("retail.templates.usecases.update_library_template.Template")
    def test_get_template_success(self, mock_template_model):
        mock_template = MagicMock()
        mock_template_model.objects.get.return_value = mock_template

        result = self.use_case._get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(uuid=self.template_uuid)
        self.assertEqual(result, mock_template)

    @patch("retail.templates.usecases.update_library_template.Template")
    def test_get_template_not_found(self, mock_template_model):
        mock_template_model.DoesNotExist = Exception
        mock_template_model.objects.get.side_effect = mock_template_model.DoesNotExist()

        with self.assertRaises(NotFound) as context:
            self.use_case._get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(uuid=self.template_uuid)
        self.assertEqual(
            str(context.exception), f"Template not found: {self.template_uuid}"
        )

    def test_update_template_metadata_with_buttons(self):
        mock_template = MagicMock()
        mock_template.metadata = {"name": "Test Template"}

        payload = {
            "library_template_button_inputs": [
                {
                    "type": "URL",
                    "text": "Ver detalhes",
                    "url": {
                        "base_url": "https://example.com",
                        "url_suffix_example": "/product/123",
                    },
                }
            ]
        }

        self.use_case._update_template_metadata(mock_template, payload)

        expected_buttons = [
            {
                "type": "URL",
                "text": "Ver detalhes",
                "url": "https://example.com",
                "example": ["/product/123"],
            }
        ]

        self.assertEqual(mock_template.metadata["buttons"], expected_buttons)
        mock_template.save.assert_called_once()

    def test_update_template_metadata_without_url_suffix_example(self):
        mock_template = MagicMock()
        mock_template.metadata = {"name": "Test Template"}

        payload = {
            "library_template_button_inputs": [
                {
                    "type": "URL",
                    "text": "Ver detalhes",
                    "url": {"base_url": "https://example.com"},
                }
            ]
        }

        self.use_case._update_template_metadata(mock_template, payload)

        expected_buttons = [
            {"type": "URL", "text": "Ver detalhes", "url": "https://example.com"}
        ]

        self.assertEqual(mock_template.metadata["buttons"], expected_buttons)
        mock_template.save.assert_called_once()

    def test_update_template_metadata_with_default_values(self):
        mock_template = MagicMock()
        mock_template.metadata = {"name": "Test Template"}

        payload = {
            "library_template_button_inputs": [
                {"url": {"base_url": "https://example.com"}}
            ]
        }

        self.use_case._update_template_metadata(mock_template, payload)

        expected_buttons = [
            {"type": "URL", "text": "Ver detalhes", "url": "https://example.com"}
        ]

        self.assertEqual(mock_template.metadata["buttons"], expected_buttons)
        mock_template.save.assert_called_once()

    def test_update_template_metadata_with_none_metadata(self):
        mock_template = MagicMock()
        mock_template.metadata = None

        payload = {
            "library_template_button_inputs": [
                {
                    "type": "URL",
                    "text": "Ver detalhes",
                    "url": {"base_url": "https://example.com"},
                }
            ]
        }

        self.use_case._update_template_metadata(mock_template, payload)

        expected_buttons = [
            {"type": "URL", "text": "Ver detalhes", "url": "https://example.com"}
        ]

        self.assertEqual(mock_template.metadata["buttons"], expected_buttons)
        mock_template.save.assert_called_once()

    def test_update_template_metadata_without_button_inputs(self):
        mock_template = MagicMock()
        mock_template.metadata = {"name": "Test Template"}

        payload = {}

        self.use_case._update_template_metadata(mock_template, payload)

        mock_template.save.assert_not_called()

    def test_build_payload(self):
        mock_template = MagicMock()
        mock_template.name = "Test Template"
        mock_template.metadata = {
            "category": "marketing",
            "language": "pt_BR",
        }
        # No integrated agent - language resolves from metadata
        mock_template.integrated_agent = None

        payload = UpdateLibraryTemplateData(
            template_uuid=self.template_uuid,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            library_template_button_inputs=[
                {
                    "type": "URL",
                    "text": "Ver detalhes",
                    "url": {"base_url": "https://example.com"},
                }
            ],
        )

        result = self.use_case._build_payload(mock_template, payload)

        expected_payload = {
            "library_template_name": "Test Template",
            "category": "marketing",
            "language": "pt_BR",
            "app_uuid": self.app_uuid,
            "project_uuid": self.project_uuid,
            "library_template_button_inputs": [
                {
                    "type": "URL",
                    "text": "Ver detalhes",
                    "url": {"base_url": "https://example.com"},
                }
            ],
        }

        self.assertEqual(result, expected_payload)

    def test_get_last_version(self):
        mock_template = MagicMock()
        mock_version = MagicMock()
        mock_template.versions.order_by.return_value.first.return_value = mock_version

        result = self.use_case._get_last_version(mock_template)

        mock_template.versions.order_by.assert_called_once_with("-id")
        mock_template.versions.order_by.return_value.first.assert_called_once()
        self.assertEqual(result, mock_version)

    @patch.object(UpdateLibraryTemplateUseCase, "_get_template")
    @patch.object(UpdateLibraryTemplateUseCase, "_get_last_version")
    @patch.object(UpdateLibraryTemplateUseCase, "_build_payload")
    @patch.object(UpdateLibraryTemplateUseCase, "_update_template_metadata")
    @patch.object(UpdateLibraryTemplateUseCase, "notify_integrations")
    def test_execute_success(
        self,
        mock_notify_integrations,
        mock_update_metadata,
        mock_build_payload,
        mock_get_last_version,
        mock_get_template,
    ):
        mock_template = MagicMock()
        mock_template.needs_button_edit = True
        mock_get_template.return_value = mock_template

        mock_version = MagicMock()
        mock_version.template_name = "Test Template"
        mock_version.uuid = self.version_uuid
        mock_get_last_version.return_value = mock_version

        built_payload = {
            "library_template_name": "Test Template",
            "category": "marketing",
            "language": "pt_BR",
            "app_uuid": self.app_uuid,
            "project_uuid": self.project_uuid,
            "library_template_button_inputs": self.payload[
                "library_template_button_inputs"
            ],
        }
        mock_build_payload.return_value = built_payload

        result = self.use_case.execute(self.payload)

        mock_get_template.assert_called_once_with(self.template_uuid)
        self.assertFalse(mock_template.needs_button_edit)

        mock_get_last_version.assert_called_once_with(mock_template)
        mock_build_payload.assert_called_once_with(mock_template, self.payload)
        mock_update_metadata.assert_called_once_with(mock_template, built_payload)
        mock_notify_integrations.assert_called_once_with(
            "Test Template", self.version_uuid, built_payload
        )

        self.assertEqual(result, mock_template)

    @patch.object(UpdateLibraryTemplateUseCase, "_get_template")
    def test_execute_template_not_found(self, mock_get_template):
        mock_get_template.side_effect = NotFound(
            f"Template not found: {self.template_uuid}"
        )

        with self.assertRaises(NotFound):
            self.use_case.execute(self.payload)

        mock_get_template.assert_called_once_with(self.template_uuid)
