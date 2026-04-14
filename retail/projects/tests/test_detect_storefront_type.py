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
        self.mock_connect_service = MagicMock()
        self.usecase = DetectStorefrontTypeUseCase(
            crawler_client=MagicMock(),
            connect_client=MagicMock(),
        )
        self.usecase.crawler_service = self.mock_crawler_service
        self.usecase.connect_service = self.mock_connect_service

    def test_sends_storefront_type_to_connect(self):
        self.mock_crawler_service.detect_storefront_type.return_value = {
            "store_url": "https://www.mystore.com.br/",
            "storefront_type": "vtex_io",
        }

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.mock_connect_service.update_project_config.assert_called_once_with(
            project_uuid=str(self.project.uuid),
            config={"storefront_type": "vtex_io"},
        )

    def test_does_not_call_connect_on_service_failure(self):
        self.mock_crawler_service.detect_storefront_type.return_value = None

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.mock_connect_service.update_project_config.assert_not_called()

    def test_does_not_raise_on_crawler_exception(self):
        self.mock_crawler_service.detect_storefront_type.side_effect = RuntimeError(
            "connection error"
        )

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.mock_connect_service.update_project_config.assert_not_called()

    def test_does_not_raise_on_connect_exception(self):
        self.mock_crawler_service.detect_storefront_type.return_value = {
            "store_url": "https://www.mystore.com.br/",
            "storefront_type": "vtex_io",
        }
        self.mock_connect_service.update_project_config.side_effect = RuntimeError(
            "connect down"
        )

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.mock_connect_service.update_project_config.assert_called_once()

    def test_skipped_when_project_is_none(self):
        self.usecase.execute(None, "https://www.mystore.com.br/")

        self.mock_crawler_service.detect_storefront_type.assert_not_called()
        self.mock_connect_service.update_project_config.assert_not_called()

    def test_no_call_when_response_missing_storefront_type(self):
        self.mock_crawler_service.detect_storefront_type.return_value = {
            "store_url": "https://www.mystore.com.br/",
        }

        self.usecase.execute(self.project, "https://www.mystore.com.br/")

        self.mock_connect_service.update_project_config.assert_not_called()
