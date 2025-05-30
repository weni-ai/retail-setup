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
                {"data": [{"name": "valid_template", "body": "new content"}]}
                if name == "valid_template"
                else {"data": []}
            )
        )
        self.usecase = ValidatePreApprovedTemplatesUseCase(
            meta_service=self.meta_service_mock
        )

    def test_get_template_info_returns_info_when_exists(self):
        info = self.usecase._get_template_info("valid_template", "pt_BR")
        self.meta_service_mock.get_pre_approved_template.assert_called_with(
            "valid_template", "pt_BR"
        )

        data = {"name": info.get("name"), "content": info.get("content")}
        self.assertEqual(data, {"name": "valid_template", "content": "new content"})

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

        self.assertFalse(self.template_invalid.is_valid)
        self.assertEqual(self.template_invalid.content, "should not change")

    def test_execute_with_no_templates(self):
        self.agent.templates.clear()
        self.usecase.execute(self.agent)

        self.meta_service_mock.get_pre_approved_template.assert_not_called()
