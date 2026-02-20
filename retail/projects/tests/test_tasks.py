from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.tasks import (
    _lock_key,
    acquire_task_lock,
    release_task_lock,
)


class TestTaskLocking(TestCase):
    @patch("retail.projects.tasks.cache")
    def test_acquire_lock_calls_cache_add(self, mock_cache):
        mock_cache.add.return_value = True

        result = acquire_task_lock("configure_nexus", "mystore")

        self.assertTrue(result)
        mock_cache.add.assert_called_once_with(
            _lock_key("configure_nexus", "mystore"),
            True,
            timeout=1800,
        )

    @patch("retail.projects.tasks.cache")
    def test_acquire_lock_returns_false_when_held(self, mock_cache):
        mock_cache.add.return_value = False

        result = acquire_task_lock("configure_nexus", "mystore")

        self.assertFalse(result)

    @patch("retail.projects.tasks.cache")
    def test_release_lock_calls_cache_delete(self, mock_cache):
        release_task_lock("configure_nexus", "mystore")

        mock_cache.delete.assert_called_once_with(
            _lock_key("configure_nexus", "mystore")
        )

    def test_lock_key_format(self):
        key = _lock_key("configure_nexus", "mystore")
        self.assertEqual(key, "task_lock:configure_nexus:mystore")


class TestTaskWaitAndStartCrawl(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

    @patch("retail.projects.tasks.StartCrawlUseCase")
    def test_starts_crawl_when_project_linked(self, mock_crawl_cls):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
        )

        mock_instance = MagicMock()
        mock_crawl_cls.return_value = mock_instance

        from retail.projects.tasks import task_wait_and_start_crawl

        task_wait_and_start_crawl("mystore", "https://mystore.com.br/")

        mock_instance.execute.assert_called_once_with(
            "mystore", "https://mystore.com.br/"
        )

    def test_retries_when_project_not_linked(self):
        ProjectOnboarding.objects.create(vtex_account="mystore")

        from celery.exceptions import Retry
        from retail.projects.tasks import task_wait_and_start_crawl

        with patch.object(
            task_wait_and_start_crawl, "retry", side_effect=Retry()
        ) as mock_retry:
            with self.assertRaises(Retry):
                task_wait_and_start_crawl("mystore", "https://mystore.com.br/")
            mock_retry.assert_called_once()


class TestTaskConfigureNexus(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
        )

    @patch("retail.projects.tasks.task_configure_wwc")
    @patch("retail.projects.tasks.ConfigureAgentBuilderUseCase")
    @patch("retail.projects.tasks.release_task_lock")
    def test_calls_agent_builder_and_dispatches_wwc(
        self, mock_release, mock_agent_cls, mock_wwc_task
    ):
        mock_instance = MagicMock()
        mock_agent_cls.return_value = mock_instance

        from retail.projects.tasks import task_configure_nexus

        task_configure_nexus("mystore", [{"link": "a", "title": "b", "content": "c"}])

        mock_instance.execute.assert_called_once_with(
            "mystore", [{"link": "a", "title": "b", "content": "c"}]
        )
        mock_release.assert_called_once_with("configure_nexus", "mystore")
        mock_wwc_task.delay.assert_called_once_with("mystore")

    @patch("retail.projects.tasks.task_configure_wwc")
    @patch("retail.projects.tasks.ConfigureAgentBuilderUseCase")
    @patch("retail.projects.tasks.release_task_lock")
    def test_releases_lock_on_failure(
        self, mock_release, mock_agent_cls, mock_wwc_task
    ):
        mock_instance = MagicMock()
        mock_instance.execute.side_effect = Exception("upload failed")
        mock_agent_cls.return_value = mock_instance

        from retail.projects.tasks import task_configure_nexus

        with self.assertRaises(Exception):
            task_configure_nexus("mystore", [])

        mock_release.assert_called_once_with("configure_nexus", "mystore")
        mock_wwc_task.delay.assert_not_called()


class TestTaskConfigureWWC(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
        )

    @patch("retail.projects.tasks.ConfigureWWCUseCase")
    def test_calls_wwc_usecase(self, mock_wwc_cls):
        mock_instance = MagicMock()
        mock_wwc_cls.return_value = mock_instance

        from retail.projects.tasks import task_configure_wwc

        task_configure_wwc("mystore")

        mock_instance.execute.assert_called_once_with("mystore")

    @patch("retail.projects.tasks.ConfigureWWCUseCase")
    def test_raises_on_failure(self, mock_wwc_cls):
        mock_instance = MagicMock()
        mock_instance.execute.side_effect = Exception("config failed")
        mock_wwc_cls.return_value = mock_instance

        from retail.projects.tasks import task_configure_wwc

        with self.assertRaises(Exception):
            task_configure_wwc("mystore")
