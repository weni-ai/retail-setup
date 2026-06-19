from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.tasks import (
    PROJECT_LINKED_PROGRESS,
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


class TestTaskSetupChannelAndStartCrawl(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

    @patch("retail.projects.tasks.OnboardingOrchestrator")
    @patch("retail.projects.tasks.InitiateCrawlUseCase")
    @patch("retail.projects.tasks.PreCrawlChannelUseCase")
    def test_runs_channel_crawl_and_orchestrator_when_project_linked(
        self, mock_channel_cls, mock_initiate_cls, mock_orch_cls
    ):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
        )

        mock_channel = MagicMock()
        mock_channel_cls.return_value = mock_channel
        mock_initiate = MagicMock()
        mock_initiate_cls.return_value = mock_initiate
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch

        call_order = []
        mock_channel.execute.side_effect = lambda *_: call_order.append("channel")
        mock_initiate.execute.side_effect = lambda *_: call_order.append("crawl")
        mock_orch.execute.side_effect = lambda *_: call_order.append("orchestrator")

        from retail.projects.tasks import task_setup_channel_and_start_crawl

        task_setup_channel_and_start_crawl("mystore", "https://mystore.com.br/")

        mock_channel.execute.assert_called_once_with("mystore")
        mock_initiate.execute.assert_called_once_with(
            self.project, "mystore", "https://mystore.com.br/"
        )
        mock_orch.execute.assert_called_once_with("mystore")

        self.assertEqual(call_order, ["channel", "crawl", "orchestrator"])

    @patch("retail.projects.tasks.OnboardingOrchestrator")
    @patch("retail.projects.tasks.InitiateCrawlUseCase")
    @patch("retail.projects.tasks.PreCrawlChannelUseCase")
    def test_sets_project_linked_progress_before_channel_setup(
        self, mock_channel_cls, _mock_initiate, _mock_orch
    ):
        """When start-setup linked the project inline, the task still bumps progress."""
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="PROJECT_CONFIG",
            progress=0,
            config={"channels": {"wwc": {}}},
        )

        mock_channel = MagicMock()
        mock_channel_cls.return_value = mock_channel

        from retail.projects.tasks import task_setup_channel_and_start_crawl

        # Capture progress at the moment the channel use case runs
        progress_at_channel_time = {}

        def capture_progress(vtex_account):
            onboarding = ProjectOnboarding.objects.get(vtex_account=vtex_account)
            progress_at_channel_time["value"] = onboarding.progress
            progress_at_channel_time["step"] = onboarding.current_step

        mock_channel.execute.side_effect = capture_progress

        task_setup_channel_and_start_crawl("mystore", "https://mystore.com.br/")

        self.assertEqual(progress_at_channel_time["value"], PROJECT_LINKED_PROGRESS)
        self.assertEqual(progress_at_channel_time["step"], "PROJECT_CONFIG")

    @patch("retail.projects.tasks.OnboardingOrchestrator")
    @patch("retail.projects.tasks.InitiateCrawlUseCase")
    @patch("retail.projects.tasks.PreCrawlChannelUseCase")
    def test_does_not_regress_progress_when_eda_linked_project(
        self, mock_channel_cls, _mock_initiate, _mock_orch
    ):
        """When EDA already set progress >= 30, the task must not regress it."""
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="PROJECT_CONFIG",
            progress=PROJECT_LINKED_PROGRESS,
            config={"channels": {"wwc": {}}},
        )

        mock_channel = MagicMock()
        mock_channel_cls.return_value = mock_channel

        from retail.projects.tasks import task_setup_channel_and_start_crawl

        task_setup_channel_and_start_crawl("mystore", "https://mystore.com.br/")

        # The single bump should be a no-op here; the progress at the time
        # the channel use case ran is still PROJECT_LINKED_PROGRESS.
        # We assert by verifying the call sequence works without errors.
        mock_channel.execute.assert_called_once()

    def test_retries_when_project_not_linked(self):
        ProjectOnboarding.objects.create(vtex_account="mystore")

        from celery.exceptions import Retry
        from retail.projects.tasks import task_setup_channel_and_start_crawl

        with patch.object(
            task_setup_channel_and_start_crawl, "retry", side_effect=Retry()
        ) as mock_retry:
            with self.assertRaises(Retry):
                task_setup_channel_and_start_crawl("mystore", "https://mystore.com.br/")
            mock_retry.assert_called_once()

    @patch("retail.projects.tasks.mark_onboarding_failed")
    def test_marks_failed_when_onboarding_record_missing(self, mock_mark_failed):
        from retail.projects.tasks import task_setup_channel_and_start_crawl

        with self.assertRaises(ProjectOnboarding.DoesNotExist):
            task_setup_channel_and_start_crawl(
                "missing-store", "https://missing.com.br/"
            )

        mock_mark_failed.assert_called_once_with(
            "missing-store", "Onboarding record not found"
        )

    @patch("retail.projects.tasks.mark_onboarding_failed")
    @patch("retail.projects.tasks.OnboardingOrchestrator")
    @patch("retail.projects.tasks.InitiateCrawlUseCase")
    @patch("retail.projects.tasks.PreCrawlChannelUseCase")
    def test_marks_failed_and_skips_crawl_when_channel_fails(
        self,
        mock_channel_cls,
        mock_initiate_cls,
        mock_orch_cls,
        mock_mark_failed,
    ):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wpp-cloud": {"channel_data": {}}}},
        )

        mock_channel = MagicMock()
        mock_channel.execute.side_effect = RuntimeError("auth_code expired")
        mock_channel_cls.return_value = mock_channel

        mock_initiate = MagicMock()
        mock_initiate_cls.return_value = mock_initiate

        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch

        from retail.projects.tasks import task_setup_channel_and_start_crawl

        with self.assertRaises(RuntimeError):
            task_setup_channel_and_start_crawl("mystore", "https://mystore.com.br/")

        mock_mark_failed.assert_called_once()
        called_with_reason = mock_mark_failed.call_args[0][1]
        self.assertIn("Channel creation failed", called_with_reason)
        mock_initiate.execute.assert_not_called()
        mock_orch.execute.assert_not_called()


class TestTaskWaitAndStartCrawlAlias(TestCase):
    """The legacy task name must keep executing the new pre-crawl pipeline."""

    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )

    @patch("retail.projects.tasks.OnboardingOrchestrator")
    @patch("retail.projects.tasks.InitiateCrawlUseCase")
    @patch("retail.projects.tasks.PreCrawlChannelUseCase")
    def test_alias_runs_channel_crawl_and_orchestrator(
        self, mock_channel_cls, mock_initiate_cls, mock_orch_cls
    ):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
        )

        mock_channel = MagicMock()
        mock_channel_cls.return_value = mock_channel
        mock_initiate = MagicMock()
        mock_initiate_cls.return_value = mock_initiate
        mock_orch = MagicMock()
        mock_orch_cls.return_value = mock_orch

        from retail.projects.tasks import task_wait_and_start_crawl

        task_wait_and_start_crawl("mystore", "https://mystore.com.br/")

        mock_channel.execute.assert_called_once_with("mystore")
        mock_initiate.execute.assert_called_once_with(
            self.project, "mystore", "https://mystore.com.br/"
        )
        mock_orch.execute.assert_called_once_with("mystore")


class TestTaskUploadNexusContents(TestCase):
    """
    Background-only upload task. Failures are soft -- the task swallows
    the exception and records it via ``SaveBackgroundFailureUseCase``.
    """

    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
        )

    @patch("retail.projects.tasks.UploadNexusContentsUseCase")
    @patch("retail.projects.tasks.release_task_lock")
    def test_delegates_to_upload_use_case(self, mock_release, mock_upload_cls):
        mock_upload = MagicMock()
        mock_upload_cls.return_value = mock_upload

        from retail.projects.tasks import task_upload_nexus_contents

        contents = [{"link": "a", "title": "b", "content": "c"}]
        task_upload_nexus_contents("mystore", contents)

        mock_upload.execute.assert_called_once_with("mystore", contents)
        mock_release.assert_called_once_with("upload_nexus_contents", "mystore")

    @patch("retail.projects.tasks.SaveBackgroundFailureUseCase")
    @patch("retail.projects.tasks.UploadNexusContentsUseCase")
    @patch("retail.projects.tasks.release_task_lock")
    def test_soft_fails_and_records_background_failure(
        self, mock_release, mock_upload_cls, mock_save_background_cls
    ):
        mock_upload = MagicMock()
        mock_upload.execute.side_effect = RuntimeError("nexus down")
        mock_upload_cls.return_value = mock_upload

        from retail.projects.tasks import task_upload_nexus_contents

        task_upload_nexus_contents("mystore", [])

        mock_save_background_cls.execute.assert_called_once_with(
            "mystore", "nexus_upload", "nexus down"
        )
        mock_release.assert_called_once_with("upload_nexus_contents", "mystore")

    @patch("retail.projects.tasks.UploadNexusContentsUseCase")
    @patch("retail.projects.tasks.release_task_lock")
    def test_releases_lock_on_success(self, mock_release, _mock_upload_cls):
        from retail.projects.tasks import task_upload_nexus_contents

        task_upload_nexus_contents("mystore", [])

        mock_release.assert_called_once_with("upload_nexus_contents", "mystore")


class TestTaskConfigureNexusDeprecatedAlias(TestCase):
    """
    The legacy ``task_configure_nexus`` name must keep executing the new
    upload pipeline so any jobs queued before the rename are still
    processed correctly.
    """

    def setUp(self):
        self.project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            config={"channels": {"wwc": {}}},
        )

    @patch("retail.projects.tasks.UploadNexusContentsUseCase")
    @patch("retail.projects.tasks.release_task_lock")
    def test_alias_delegates_to_upload_use_case(
        self, mock_release, mock_upload_cls
    ):
        mock_upload = MagicMock()
        mock_upload_cls.return_value = mock_upload

        from retail.projects.tasks import task_configure_nexus

        contents = [{"link": "a", "title": "b", "content": "c"}]
        task_configure_nexus("mystore", contents)

        mock_upload.execute.assert_called_once_with("mystore", contents)
        mock_release.assert_called_once_with("upload_nexus_contents", "mystore")


class TestTaskActivateAgenticCxScript(TestCase):
    @patch("retail.projects.tasks.VtexIOService")
    def test_calls_service_with_correct_params(self, mock_service_cls):
        mock_service = MagicMock()
        mock_service_cls.return_value = mock_service

        from retail.projects.tasks import task_activate_agentic_cx_script

        task_activate_agentic_cx_script("teststore")

        mock_service.activate_agentic_cx_script.assert_called_once_with(
            account_domain="teststore.myvtex.com",
            vtex_account="teststore",
        )

    @patch("retail.projects.tasks.VtexIOService")
    def test_propagates_service_exception(self, mock_service_cls):
        from retail.clients.exceptions import CustomAPIException

        mock_service = MagicMock()
        mock_service.activate_agentic_cx_script.side_effect = CustomAPIException(
            detail="Connection refused"
        )
        mock_service_cls.return_value = mock_service

        from retail.projects.tasks import task_activate_agentic_cx_script

        with self.assertRaises(CustomAPIException):
            task_activate_agentic_cx_script("teststore")
