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

        result = self.use_case.get_template(self.template_uuid)

        mock_template_model.objects.get.assert_called_once_with(
            uuid=self.template_uuid, is_active=True
        )
        self.assertEqual(result, mock_template)

    @patch("retail.templates.usecases.delete_template.Template")
    def test_get_template_not_found(self, mock_template_model):
        mock_template_model.DoesNotExist = Exception
        mock_template_model.objects.get.side_effect = mock_template_model.DoesNotExist()

        with self.assertRaises(NotFound) as context:
            self.use_case.get_template(self.template_uuid)

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

    @patch.object(DeleteTemplateUseCase, "_add_template_to_ignore_list")
    def test_execute_success(self, mock_add_to_ignore_list):
        mock_template = MagicMock()
        mock_template.is_active = True

        self.use_case.execute(mock_template)

        mock_add_to_ignore_list.assert_called_once_with(mock_template)
        self.assertFalse(mock_template.is_active)
        mock_template.save.assert_called_once()
