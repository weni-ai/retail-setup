from unittest.mock import MagicMock, Mock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.initiate_crawl import InitiateCrawlUseCase


class TestInitiateCrawlUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
            language="pt-br",
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
        )
        self.mock_connect = Mock()
        self.mock_start_crawl = MagicMock()
        self.mock_detect_storefront = MagicMock()

        self.usecase = InitiateCrawlUseCase(connect_service=self.mock_connect)
        self.usecase.start_crawl_usecase = self.mock_start_crawl
        self.usecase.detect_storefront_usecase = self.mock_detect_storefront

    def test_runs_full_sequence(self):
        self.usecase.execute(
            self.project, "mystore", "https://www.mystore.com.br/"
        )

        self.mock_connect.update_project_config.assert_called_once()
        self.mock_start_crawl.execute.assert_called_once_with(
            "mystore", "https://www.mystore.com.br/"
        )
        self.mock_detect_storefront.execute.assert_called_once_with(
            self.project, "https://www.mystore.com.br/"
        )

    def test_sends_vtex_host_store_with_correct_args(self):
        self.usecase.execute(
            self.project, "mystore", "https://www.mystore.com.br/"
        )

        self.mock_connect.update_project_config.assert_called_once_with(
            project_uuid=str(self.project.uuid),
            config={"vtex_host_store": "https://www.mystore.com.br/"},
        )

    def test_crawl_proceeds_when_connect_fails(self):
        self.mock_connect.update_project_config.side_effect = Exception(
            "connect down"
        )

        self.usecase.execute(
            self.project, "mystore", "https://www.mystore.com.br/"
        )

        self.mock_start_crawl.execute.assert_called_once()
        self.mock_detect_storefront.execute.assert_called_once()

    def test_storefront_detection_skipped_when_start_crawl_raises(self):
        """
        ``StartCrawlUseCase`` soft-fails on crawler-comms errors (does NOT
        raise), but it can still raise on unexpected errors (e.g. DB
        lookup failures). When it does raise, storefront detection must
        be skipped so the failure surface stays narrow.
        """
        self.mock_start_crawl.execute.side_effect = RuntimeError("unexpected boom")

        with self.assertRaises(RuntimeError):
            self.usecase.execute(
                self.project, "mystore", "https://www.mystore.com.br/"
            )

        self.mock_detect_storefront.execute.assert_not_called()
