from unittest.mock import patch, MagicMock
from uuid import uuid4
from django.test import TestCase
from rest_framework.exceptions import NotFound

from retail.templates.usecases.delete_template import DeleteTemplateUseCase


class TestDeleteTemplateUseCase(TestCase):
    def setUp(self):
        self.use_case = DeleteTemplateUseCase()
        self.template_uuid = uuid4()

    @patch("retail.templates.usecases.delete_template.Template")
    def test_get_template_success(self, mock_template_model):
        mock_template = MagicMock()
        mock_template_model.objects.get.return_value = mock_template

        result = self.use_case._get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(
            uuid=self.template_uuid, is_active=True
        )
        self.assertEqual(result, mock_template)

    @patch("retail.templates.usecases.delete_template.Template")
    def test_get_template_not_found(self, mock_template_model):
        mock_template_model.DoesNotExist = Exception
        mock_template_model.objects.get.side_effect = mock_template_model.DoesNotExist()

        with self.assertRaises(NotFound) as context:
            self.use_case._get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(
            uuid=self.template_uuid, is_active=True
        )
        self.assertEqual(
            str(context.exception), f"Template not found: {self.template_uuid}"
        )

    def test_add_template_to_ignore_list(self):
        mock_template = MagicMock()
        mock_integrated_agent = MagicMock()
        mock_template.integrated_agent = mock_integrated_agent
        mock_template.parent.slug = "test-template-slug"
        mock_integrated_agent.ignore_templates = []

        self.use_case._add_template_to_ignore_list(mock_template)

        self.assertIn("test-template-slug", mock_integrated_agent.ignore_templates)
        mock_integrated_agent.save.assert_called_once()

    @patch.object(DeleteTemplateUseCase, "_get_template")
    @patch.object(DeleteTemplateUseCase, "_add_template_to_ignore_list")
    def test_execute_custom_template(self, mock_add_to_ignore_list, mock_get_template):
        mock_template = MagicMock()
        mock_template.is_custom = True
        mock_get_template.return_value = mock_template

        self.use_case.execute(self.template_uuid)

        mock_get_template.assert_called_once_with(self.template_uuid)
        mock_add_to_ignore_list.assert_not_called()
        self.assertFalse(mock_template.is_active)
        mock_template.save.assert_called_once()

    @patch.object(DeleteTemplateUseCase, "_get_template")
    @patch.object(DeleteTemplateUseCase, "_add_template_to_ignore_list")
    def test_execute_non_custom_template(
        self, mock_add_to_ignore_list, mock_get_template
    ):
        mock_template = MagicMock()
        mock_template.is_custom = False
        mock_get_template.return_value = mock_template

        self.use_case.execute(self.template_uuid)

        mock_get_template.assert_called_once_with(self.template_uuid)
        mock_add_to_ignore_list.assert_called_once_with(mock_template)
        self.assertFalse(mock_template.is_active)
        mock_template.save.assert_called_once()

    @patch.object(DeleteTemplateUseCase, "_get_template")
    def test_execute_template_not_found(self, mock_get_template):
        mock_get_template.side_effect = NotFound(
            f"Template not found: {self.template_uuid}"
        )

        with self.assertRaises(NotFound):
            self.use_case.execute(self.template_uuid)

        mock_get_template.assert_called_once_with(self.template_uuid)
