from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.projects.usecases.detect_storefront_type import (
    DetectStorefrontTypeUseCase,
)


class TestDetectStorefrontTypeUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
            language="pt-br",
        )
        self.mock_crawler_service = MagicMock()
        self.usecase = DetectStorefrontTypeUseCase(crawler_client=MagicMock())
        self.usecase.crawler_service = self.mock_crawler_service

    def test_stores_storefront_type_in_project_config(self):
        self.mock_crawler_service.detect_storefront_type.return_value = {
            "store_url": "https://www.mystore.com.br/",
            "storefront_type": "vtex_io",
        }

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.project.refresh_from_db()
        self.assertEqual(self.project.config["storefront_type"], "vtex_io")

    def test_does_not_raise_on_service_failure(self):
        self.mock_crawler_service.detect_storefront_type.return_value = None

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.project.refresh_from_db()
        self.assertNotIn("storefront_type", self.project.config)

    def test_does_not_raise_on_exception(self):
        self.mock_crawler_service.detect_storefront_type.side_effect = RuntimeError(
            "connection error"
        )

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.project.refresh_from_db()
        self.assertNotIn("storefront_type", self.project.config)

    def test_preserves_existing_project_config(self):
        self.project.config = {"existing_key": "value"}
        self.project.save(update_fields=["config"])

        self.mock_crawler_service.detect_storefront_type.return_value = {
            "store_url": "https://www.mystore.com.br/",
            "storefront_type": "faststore",
        }

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.project.refresh_from_db()
        self.assertEqual(self.project.config["storefront_type"], "faststore")
        self.assertEqual(self.project.config["existing_key"], "value")

    def test_skipped_when_project_is_none(self):
        self.usecase.execute(None, "https://www.mystore.com.br/")

        self.mock_crawler_service.detect_storefront_type.assert_not_called()

    def test_no_write_when_response_missing_storefront_type(self):
        self.mock_crawler_service.detect_storefront_type.return_value = {
            "store_url": "https://www.mystore.com.br/",
        }

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.project.refresh_from_db()
        self.assertNotIn("storefront_type", self.project.config)
