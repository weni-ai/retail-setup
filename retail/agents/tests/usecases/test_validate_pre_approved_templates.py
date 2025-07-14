from unittest.mock import Mock

from django.test import TestCase

from uuid import uuid4

from retail.projects.models import Project
from retail.agents.models import Agent, PreApprovedTemplate
from retail.agents.usecases import ValidatePreApprovedTemplatesUseCase


class ValidatePreApprovedTemplatesUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.agent = Agent.objects.create(
            name="Test Agent", project=self.project, language="pt_BR"
        )

        self.template_valid = PreApprovedTemplate.objects.create(
            name="valid_template",
            content="old content",
            is_valid=False,
        )
        self.template_invalid = PreApprovedTemplate.objects.create(
            name="invalid_template",
            content="should not change",
            is_valid=True,
        )
        self.agent.templates.set([self.template_valid, self.template_invalid])

        self.meta_service_mock = Mock()
        self.meta_service_mock.get_pre_approved_template.side_effect = (
            lambda name, language: (
                {
                    "data": [
                        {
                            "name": "valid_template",
                            "body": "new content",
                            "header": {"type": "TEXT", "text": "Header"},
                            "body_params": ["param1", "param2"],
                            "footer": "Footer text",
                            "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
                            "category": "MARKETING",
                            "language": "pt_BR",
                        }
                    ]
                }
                if name == "valid_template"
                else {"data": []}
            )
        )

        self.template_adapter_mock = Mock()
        self.template_adapter_mock.header_transformer.transform.return_value = {
            "type": "TEXT",
            "text": "Header",
        }

        self.usecase = ValidatePreApprovedTemplatesUseCase(
            meta_service=self.meta_service_mock,
            template_adapter=self.template_adapter_mock,
        )

    def test_get_template_info_returns_info_when_exists(self):
        info = self.usecase._get_template_info("valid_template", "pt_BR")

        self.meta_service_mock.get_pre_approved_template.assert_called_with(
            "valid_template", "pt_BR"
        )
        self.template_adapter_mock.header_transformer.transform.assert_called_with(
            {"type": "TEXT", "text": "Header"}
        )

        expected_info = {
            "name": "valid_template",
            "content": "new content",
            "metadata": {
                "header": {"type": "TEXT", "text": "Header"},
                "body": "new content",
                "body_params": ["param1", "param2"],
                "footer": "Footer text",
                "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
                "category": "MARKETING",
                "language": "pt_BR",
            },
        }

        self.assertEqual(info, expected_info)

    def test_get_template_info_returns_none_when_not_exists(self):
        info = self.usecase._get_template_info("invalid_template", "pt_BR")

        self.meta_service_mock.get_pre_approved_template.assert_called_with(
            "invalid_template", "pt_BR"
        )
        self.assertIsNone(info)

    def test_execute_updates_templates_correctly(self):
        self.usecase.execute(self.agent)

        self.template_valid.refresh_from_db()
        self.template_invalid.refresh_from_db()

        self.assertTrue(self.template_valid.is_valid)
        self.assertEqual(self.template_valid.name, "valid_template")
        self.assertEqual(self.template_valid.content, "new content")

        expected_metadata = {
            "header": {"type": "TEXT", "text": "Header"},
            "body": "new content",
            "body_params": ["param1", "param2"],
            "footer": "Footer text",
            "buttons": [{"type": "QUICK_REPLY", "text": "Button"}],
            "category": "MARKETING",
            "language": "pt_BR",
        }
        self.assertEqual(self.template_valid.metadata, expected_metadata)

        self.assertFalse(self.template_invalid.is_valid)
        self.assertEqual(self.template_invalid.content, "should not change")

    def test_execute_with_no_templates(self):
        self.agent.templates.clear()
        self.usecase.execute(self.agent)

        self.meta_service_mock.get_pre_approved_template.assert_not_called()
        self.template_adapter_mock.header_transformer.transform.assert_not_called()

    def test_template_adapter_is_called_correctly(self):
        self.usecase._get_template_info("valid_template", "pt_BR")
        self.template_adapter_mock.header_transformer.transform.assert_called_once_with(
            {"type": "TEXT", "text": "Header"}
        )
