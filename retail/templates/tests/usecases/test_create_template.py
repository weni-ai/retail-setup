from unittest.mock import Mock

from retail.templates.usecases.create_template import (
    CreateTemplateUseCase,
    CreateTemplateData,
)

from django.test import TestCase

from retail.templates.models import Template, Version
from retail.templates.exceptions import IntegrationsServerError

from uuid import uuid4

VALID_PAYLOAD: CreateTemplateData = {
    "template_translation": {"en": {"text": "Hello"}},
    "template_name": "TestTemplate",
    "start_condition": "start",
    "category": "test",
    "app_uuid": str(uuid4()),
    "project_uuid": str(uuid4()),
}


class CreateTemplateUseCaseTest(TestCase):
    def setUp(self):
        self.mock_service = Mock()
        self.mock_service.create_template.return_value = str(uuid4())
        self.use_case = CreateTemplateUseCase(service=self.mock_service)

    def test_execute_successfully_creates_template_and_version(self):
        template = self.use_case.execute(VALID_PAYLOAD)

        self.assertIsInstance(template, Template)
        self.assertTrue(Template.objects.filter(uuid=template.uuid).exists())

        version = Version.objects.get(template=template)

        self.assertTrue(version.template_name.startswith("weni_"))
        self.assertEqual(str(version.integrations_app_uuid), VALID_PAYLOAD["app_uuid"])
        self.assertEqual(str(version.project_uuid), VALID_PAYLOAD["project_uuid"])

        self.mock_service.create_template.assert_called_once()
        self.mock_service.create_template_translation.assert_called_once()

    def test_execute_raises_error_on_service_failure(self):
        self.mock_service.create_template.side_effect = Exception("Integration error")
        use_case = CreateTemplateUseCase(service=self.mock_service)

        with self.assertRaises(IntegrationsServerError):
            use_case.execute(VALID_PAYLOAD)
