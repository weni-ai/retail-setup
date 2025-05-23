from unittest.mock import patch

from retail.templates.usecases.create_template import (
    CreateTemplateUseCase,
    CreateTemplateData,
)

from django.test import TestCase

from retail.templates.models import Template, Version
from retail.projects.models import Project

from uuid import uuid4


class CreateTemplateUseCaseTest(TestCase):
    def setUp(self):
        self.use_case = CreateTemplateUseCase()

        project_uuid = uuid4()

        self.project = Project.objects.create(name="project", uuid=project_uuid)

        self.VALID_PAYLOAD: CreateTemplateData = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "TestTemplate",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(project_uuid),
        }

    @patch("retail.templates.usecases.create_template.task_create_template.delay")
    def test_execute_successfully_creates_template_and_version(self, mock_task_delay):
        template = self.use_case.execute(self.VALID_PAYLOAD)

        self.assertIsInstance(template, Template)
        self.assertTrue(Template.objects.filter(uuid=template.uuid).exists())

        version = Version.objects.get(template=template)

        self.assertTrue(version.template_name.startswith("weni_"))
        self.assertEqual(
            str(version.integrations_app_uuid), self.VALID_PAYLOAD["app_uuid"]
        )
        self.assertEqual(str(version.project.uuid), self.VALID_PAYLOAD["project_uuid"])

        mock_task_delay.assert_called_once()
        kwargs = mock_task_delay.call_args.kwargs
        self.assertEqual(kwargs["template_name"], version.template_name)
        self.assertEqual(kwargs["app_uuid"], self.VALID_PAYLOAD["app_uuid"])
        self.assertEqual(kwargs["project_uuid"], self.VALID_PAYLOAD["project_uuid"])

    @patch("retail.templates.usecases.create_template.task_create_template.delay")
    def test_execute_creates_new_version_for_existing_template(self, mock_task_delay):
        existing_template = Template.objects.create(
            name=self.VALID_PAYLOAD["template_name"],
            current_version=None,
        )

        template = self.use_case.execute(self.VALID_PAYLOAD)

        self.assertEqual(template.uuid, existing_template.uuid)
        self.assertEqual(
            Template.objects.filter(name=existing_template.name).count(), 1
        )

        version = Version.objects.get(template=existing_template)

        self.assertTrue(version.template_name.startswith("weni_"))
        self.assertEqual(
            str(version.integrations_app_uuid), self.VALID_PAYLOAD["app_uuid"]
        )
        self.assertEqual(str(version.project.uuid), self.VALID_PAYLOAD["project_uuid"])

        mock_task_delay.assert_called_once()
