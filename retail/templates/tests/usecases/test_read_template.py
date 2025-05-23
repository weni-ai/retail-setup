from uuid import uuid4

from django.test import TestCase

from rest_framework.exceptions import NotFound

from retail.templates.models import Template
from retail.templates.usecases.read_template import ReadTemplateUseCase


class ReadTemplateUseCaseTest(TestCase):
    def setUp(self):
        self.template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
        )
        self.use_case = ReadTemplateUseCase()

    def test_execute_returns_template_when_exists(self):
        result = self.use_case.execute(self.template.uuid)
        self.assertIsInstance(result, Template)
        self.assertEqual(result.uuid, self.template.uuid)

    def test_execute_raises_not_found_when_template_does_not_exist(self):
        non_existent_uuid = uuid4()
        with self.assertRaises(NotFound):
            self.use_case.execute(non_existent_uuid)
