from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.channel_usecase_resolver import (
    CHANNEL_USECASES,
    resolve_channel_usecase,
)
from retail.projects.usecases.configure_wpp_cloud import ConfigureWPPCloudUseCase
from retail.projects.usecases.configure_wwc import ConfigureWWCUseCase
from retail.projects.usecases.pre_crawl_channel import PreCrawlChannelUseCase


class TestChannelUseCaseResolver(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

    def test_resolves_wwc_usecase(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
        )

        usecase_cls = resolve_channel_usecase("mystore")

        self.assertIs(usecase_cls, ConfigureWWCUseCase)

    def test_resolves_wpp_cloud_usecase(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wpp-cloud": {"channel_data": {}}}},
        )

        usecase_cls = resolve_channel_usecase("mystore")

        self.assertIs(usecase_cls, ConfigureWPPCloudUseCase)

    def test_raises_when_no_channel_configured(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={},
        )

        with self.assertRaises(ValueError) as ctx:
            resolve_channel_usecase("mystore")

        self.assertIn("No channel configured", str(ctx.exception))

    def test_raises_when_channel_unsupported(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"bogus": {}}},
        )

        with self.assertRaises(ValueError) as ctx:
            resolve_channel_usecase("mystore")

        self.assertIn("No channel use case registered", str(ctx.exception))

    def test_registry_lists_supported_channels(self):
        self.assertIn("wwc", CHANNEL_USECASES)
        self.assertIn("wpp-cloud", CHANNEL_USECASES)


class TestPreCrawlChannelUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

    @patch("retail.projects.usecases.pre_crawl_channel.resolve_channel_usecase")
    def test_executes_resolved_channel_usecase(self, mock_resolve):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
        )

        mock_channel_cls = MagicMock()
        mock_channel_cls.__name__ = "MockChannelUseCase"
        mock_channel_instance = MagicMock()
        mock_channel_cls.return_value = mock_channel_instance
        mock_resolve.return_value = mock_channel_cls

        PreCrawlChannelUseCase().execute("mystore")

        mock_resolve.assert_called_once_with("mystore")
        mock_channel_cls.assert_called_once_with()
        mock_channel_instance.execute.assert_called_once_with("mystore")

    @patch("retail.projects.usecases.pre_crawl_channel.resolve_channel_usecase")
    def test_propagates_channel_usecase_failure(self, mock_resolve):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wpp-cloud": {"channel_data": {}}}},
        )

        mock_channel_cls = MagicMock()
        mock_channel_cls.__name__ = "MockChannelUseCase"
        mock_channel_instance = MagicMock()
        mock_channel_instance.execute.side_effect = RuntimeError("auth_code expired")
        mock_channel_cls.return_value = mock_channel_instance
        mock_resolve.return_value = mock_channel_cls

        with self.assertRaises(RuntimeError) as ctx:
            PreCrawlChannelUseCase().execute("mystore")

        self.assertIn("auth_code expired", str(ctx.exception))
