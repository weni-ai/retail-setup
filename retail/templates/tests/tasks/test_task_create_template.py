from unittest.mock import patch, MagicMock
from django.test import TestCase


class TestTaskCreateTemplate(TestCase):
    def setUp(self):
        self.template_name = "Test Template"
        self.app_uuid = "app-123"
        self.project_uuid = "project-456"
        self.category = "marketing"
        self.version_uuid = "version-789"
        self.template_translation = {"language": "en", "content": "Test content"}

    @patch("retail.templates.tasks.IntegrationsService")
    @patch("retail.templates.usecases.update_template.UpdateTemplateUseCase")
    @patch("retail.templates.tasks.logger")
    def test_task_create_template_success(
        self, mock_logger, mock_update_use_case, mock_integrations_service
    ):
        from retail.templates.tasks import task_create_template

        mock_service_instance = MagicMock()
        mock_integrations_service.return_value = mock_service_instance
        mock_service_instance.create_template.return_value = "template-uuid-123"

        task_create_template(
            template_name=self.template_name,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=self.category,
            version_uuid=self.version_uuid,
            template_translation=self.template_translation,
        )

        mock_integrations_service.assert_called_once()
        mock_service_instance.create_template.assert_called_once_with(
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            name=self.template_name,
            category=self.category,
            gallery_version=self.version_uuid,
        )
        mock_service_instance.create_template_translation.assert_called_once_with(
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            template_uuid="template-uuid-123",
            payload=self.template_translation,
        )
        mock_logger.info.assert_called_once_with(
            f"Template created: {self.template_name} for App: {self.app_uuid} - {self.category} - version: {self.version_uuid}"  # noqa: E501
        )
        mock_update_use_case.assert_not_called()

    @patch("retail.templates.tasks.IntegrationsService")
    @patch("retail.templates.usecases.update_template.UpdateTemplateUseCase")
    @patch("retail.templates.tasks.logger")
    def test_task_create_template_failure_on_create_template(
        self, mock_logger, mock_update_use_case, mock_integrations_service
    ):
        from retail.templates.tasks import task_create_template

        mock_service_instance = MagicMock()
        mock_integrations_service.return_value = mock_service_instance
        mock_service_instance.create_template.side_effect = Exception(
            "Template creation failed"
        )

        mock_update_use_case_instance = MagicMock()
        mock_update_use_case.return_value = mock_update_use_case_instance

        task_create_template(
            template_name=self.template_name,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=self.category,
            version_uuid=self.version_uuid,
            template_translation=self.template_translation,
        )

        mock_service_instance.create_template.assert_called_once()
        mock_service_instance.create_template_translation.assert_not_called()
        mock_logger.error.assert_called_once_with(
            f"Error creating template: {self.template_name} for App: {self.app_uuid} - {self.category} - version: {self.version_uuid} Template creation failed"  # noqa: E501
        )
        mock_update_use_case.assert_called_once()
        mock_update_use_case_instance.execute.assert_called_once_with(
            payload={"version_uuid": self.version_uuid, "status": "REJECTED"}
        )
        mock_logger.info.assert_called_with(
            f"Template {self.template_name}, Version {self.version_uuid} has been marked as REJECTED."
        )

    @patch("retail.templates.tasks.IntegrationsService")
    @patch("retail.templates.usecases.update_template.UpdateTemplateUseCase")
    @patch("retail.templates.tasks.logger")
    def test_task_create_template_failure_on_create_translation(
        self, mock_logger, mock_update_use_case, mock_integrations_service
    ):
        from retail.templates.tasks import task_create_template

        mock_service_instance = MagicMock()
        mock_integrations_service.return_value = mock_service_instance
        mock_service_instance.create_template.return_value = "template-uuid-123"
        mock_service_instance.create_template_translation.side_effect = Exception(
            "Translation creation failed"
        )

        mock_update_use_case_instance = MagicMock()
        mock_update_use_case.return_value = mock_update_use_case_instance

        task_create_template(
            template_name=self.template_name,
            app_uuid=self.app_uuid,
            project_uuid=self.project_uuid,
            category=self.category,
            version_uuid=self.version_uuid,
            template_translation=self.template_translation,
        )

        mock_service_instance.create_template.assert_called_once()
        mock_service_instance.create_template_translation.assert_called_once()
        mock_logger.error.assert_called_once_with(
            f"Error creating template: {self.template_name} for App: {self.app_uuid} - {self.category} - version: {self.version_uuid} Translation creation failed"  # noqa: E501
        )
        mock_update_use_case.assert_called_once()
        mock_update_use_case_instance.execute.assert_called_once_with(
            payload={"version_uuid": self.version_uuid, "status": "REJECTED"}
        )
        mock_logger.info.assert_called_with(
            f"Template {self.template_name}, Version {self.version_uuid} has been marked as REJECTED."
        )
