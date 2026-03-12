from uuid import uuid4

from django.test import TestCase
from rest_framework.exceptions import ValidationError

from retail.projects.models import Project
from retail.vtex.usecases.get_store_url import GetStoreUrlUseCase


class TestGetStoreUrlUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Store",
            uuid=uuid4(),
            vtex_account="mystore",
            config={"vtex_host_store": "https://www.mystore.com.br/"},
        )
        self.use_case = GetStoreUrlUseCase()

    def test_returns_store_url(self):
        result = self.use_case.execute(project_uuid=str(self.project.uuid))

        self.assertEqual(result["store_url"], "https://www.mystore.com.br/")

    def test_raises_when_project_not_found(self):
        with self.assertRaises(ValidationError):
            self.use_case.execute(project_uuid=str(uuid4()))

    def test_raises_when_store_url_not_configured(self):
        project = Project.objects.create(
            name="Empty Config",
            uuid=uuid4(),
            vtex_account="emptystore",
            config={},
        )

        with self.assertRaises(ValidationError):
            self.use_case.execute(project_uuid=str(project.uuid))

    def test_raises_when_store_url_is_empty_string(self):
        project = Project.objects.create(
            name="Empty URL",
            uuid=uuid4(),
            vtex_account="emptyurl",
            config={"vtex_host_store": ""},
        )

        with self.assertRaises(ValidationError):
            self.use_case.execute(project_uuid=str(project.uuid))
