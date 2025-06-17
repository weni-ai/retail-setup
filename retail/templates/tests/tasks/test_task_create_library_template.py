from unittest.mock import patch, MagicMock

from django.test import TestCase


class TestTaskCreateLibraryTemplate(TestCase):
    def setUp(self):
        self.name = "Test Library Template"
        self.app_uuid = "app-123"
        self.project_uuid = "project-456"
        self.category = "marketing"
        self.language = "en"
        self.library_template_name = "library-template-test"
        self.gallery_version = "version-789"
        self.library_template_button_inputs = [
            {"button_id": "btn1", "label": "Button 1"},
            {"button_id": "btn2", "label": "Button 2"},
        ]

    @patch("retail.templates.tasks.IntegrationsService")
    @patch("retail.templates.tasks.UpdateTemplateUseCase")
    @patch("retail.templates.tasks.logger")
    def test_task_create_library_template_success_without_button_inputs(
        self, mock_logger, mock_update_use_case, mock_integrations_service
    ):
        from retail.templates.tasks import task_create_library_template

        mock_service_instance = MagicMock()
        mock_integrations_service.return_value = mock_service_instance

        task_create_library_template(
            name=self.name,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=self.category,
            language=self.language,
            library_template_name=self.library_template_name,
            gallery_version=self.gallery_version,
        )

        expected_payload = {
            "library_template_name": self.library_template_name,
            "name": self.name,
            "language": self.language,
            "category": self.category,
            "gallery_version": self.gallery_version,
        }

        mock_integrations_service.assert_called_once()
        mock_service_instance.create_library_template.assert_called_once_with(
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            template_data=expected_payload,
        )
        mock_update_use_case.assert_not_called()
        mock_logger.error.assert_not_called()

    @patch("retail.templates.tasks.IntegrationsService")
    @patch("retail.templates.tasks.UpdateTemplateUseCase")
    @patch("retail.templates.tasks.logger")
    def test_task_create_library_template_success_with_button_inputs(
        self, mock_logger, mock_update_use_case, mock_integrations_service
    ):
        from retail.templates.tasks import task_create_library_template

        mock_service_instance = MagicMock()
        mock_integrations_service.return_value = mock_service_instance

        task_create_library_template(
            name=self.name,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=self.category,
            language=self.language,
            library_template_name=self.library_template_name,
            gallery_version=self.gallery_version,
            library_template_button_inputs=self.library_template_button_inputs,
        )

        expected_payload = {
            "library_template_name": self.library_template_name,
            "name": self.name,
            "language": self.language,
            "category": self.category,
            "gallery_version": self.gallery_version,
            "library_template_button_inputs": self.library_template_button_inputs,
        }

        mock_integrations_service.assert_called_once()
        mock_service_instance.create_library_template.assert_called_once_with(
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            template_data=expected_payload,
        )
        mock_update_use_case.assert_not_called()
        mock_logger.error.assert_not_called()

    @patch("retail.templates.tasks.IntegrationsService")
    @patch("retail.templates.tasks.UpdateTemplateUseCase")
    @patch("retail.templates.tasks.logger")
    @patch("retail.templates.tasks.traceback")
    def test_task_create_library_template_failure(
        self,
        mock_traceback,
        mock_logger,
        mock_update_use_case,
        mock_integrations_service,
    ):
        from retail.templates.tasks import task_create_library_template

        mock_service_instance = MagicMock()
        mock_integrations_service.return_value = mock_service_instance
        mock_service_instance.create_library_template.side_effect = Exception(
            "Library template creation failed"
        )
        mock_traceback.format_exc.return_value = "Traceback details"

        mock_update_use_case_instance = MagicMock()
        mock_update_use_case.return_value = mock_update_use_case_instance

        task_create_library_template(
            name=self.name,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=self.category,
            language=self.language,
            library_template_name=self.library_template_name,
            gallery_version=self.gallery_version,
            library_template_button_inputs=self.library_template_button_inputs,
        )

        mock_service_instance.create_library_template.assert_called_once()
        mock_logger.error.assert_called_once_with(
            f"Error creating library template: {self.library_template_name} "
            f"for App: {self.app_uuid} - {self.category} - version: {self.gallery_version} Library template creation failed"  # noqa: E501
            f"Error: Traceback details"
        )
        mock_update_use_case.assert_called_once()
        mock_update_use_case_instance.execute.assert_called_once_with(
            payload={"version_uuid": self.gallery_version, "status": "REJECTED"}
        )
        mock_logger.info.assert_called_once_with(
            f"Library Template {self.library_template_name}, Version {self.gallery_version} has been marked as REJECTED."  # noqa: E501
        )
