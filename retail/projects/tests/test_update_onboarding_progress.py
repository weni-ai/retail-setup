from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_dto import CrawlerWebhookDTO
from retail.projects.usecases.update_onboarding_progress import (
    COMPLETED_EVENT,
    FAILED_EVENT,
    URL_REDIRECTED_EVENT,
    UpdateOnboardingProgressUseCase,
)


class TestUpdateOnboardingProgressUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            name="Test Project",
            uuid=uuid4(),
            vtex_account="mystore",
        )
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=self.project,
            current_step="NEXUS_CONFIG",
            progress=75,
        )
        self.onboarding_uuid = str(self.onboarding.uuid)
        self.connect_service = MagicMock()
        self.use_case = UpdateOnboardingProgressUseCase(
            connect_service=self.connect_service
        )

    # ── Progress handling ──────────────────────────────────────────

    def test_does_not_touch_main_progress_on_generic_event(self):
        """
        Crawl webhook progress events run in background and must NOT
        push the main wizard ``progress`` -- by the time these arrive
        the inline orchestrator may already be advancing
        ``NEXUS_CONFIG`` (or have completed).
        """
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=35,
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.progress, 75)

    def test_does_not_overwrite_higher_main_progress(self):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=10,
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.progress, 75)

    # ── Completed event ────────────────────────────────────────────

    @patch(
        "retail.projects.usecases.update_onboarding_progress.task_upload_nexus_contents"
    )
    @patch(
        "retail.projects.usecases.update_onboarding_progress.acquire_task_lock",
        return_value=True,
    )
    def test_completed_records_success_and_dispatches_upload_task(
        self, mock_lock, mock_task
    ):
        """
        Completion must record ``crawler_result=SUCCESS`` and dispatch
        the background nexus upload task -- WITHOUT touching the main
        ``progress``.
        """
        contents = [
            {"link": "https://mystore.com.br/", "title": "Home", "content": "Welcome"},
        ]
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=COMPLETED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=100,
            data={"contents": contents},
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.progress, 75)
        self.assertEqual(result.crawler_result, ProjectOnboarding.SUCCESS)
        mock_lock.assert_called_once_with("upload_nexus_contents", "mystore")
        mock_task.delay.assert_called_once_with("mystore", contents)

    @patch(
        "retail.projects.usecases.update_onboarding_progress.task_upload_nexus_contents"
    )
    @patch(
        "retail.projects.usecases.update_onboarding_progress.acquire_task_lock",
        return_value=False,
    )
    def test_completed_skips_dispatch_when_lock_held(self, mock_lock, mock_task):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=COMPLETED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=100,
            data={"contents": []},
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.crawler_result, ProjectOnboarding.SUCCESS)
        mock_task.delay.assert_not_called()

    # ── Failed event ───────────────────────────────────────────────

    @patch(
        "retail.projects.usecases.update_onboarding_progress."
        "SaveBackgroundFailureUseCase"
    )
    def test_failed_records_soft_failure_without_flipping_failed(
        self, mock_save_background_cls
    ):
        """
        Background crawl failures are soft -- ``onboarding.failed``
        must stay False (the main wizard is decoupled from the crawl
        outcome) and the error lands in ``config["background_error"]``
        via ``SaveBackgroundFailureUseCase``.
        """
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=FAILED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=0,
            data={"error": "Connection timeout"},
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.crawler_result, ProjectOnboarding.FAIL)
        self.assertFalse(result.failed)
        mock_save_background_cls.execute.assert_called_once_with(
            "mystore", "crawl", "Connection timeout"
        )

    # ── URL redirected event ───────────────────────────────────────

    def test_url_redirected_persists_resolved_url_and_notifies_connect(self):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=URL_REDIRECTED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com/",
            data={
                "original_url": "https://mystore.com/",
                "resolved_url": "https://www.mystore.com/",
            },
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(
            result.config.get("vtex_host_store"), "https://www.mystore.com/"
        )
        self.connect_service.update_project_config.assert_called_once_with(
            project_uuid=str(self.project.uuid),
            config={"vtex_host_store": "https://www.mystore.com/"},
        )

    def test_url_redirected_preserves_existing_config(self):
        self.onboarding.config = {"channels": {"wwc": {"channel_data": {"x": 1}}}}
        self.onboarding.save()

        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=URL_REDIRECTED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com/",
            data={
                "original_url": "https://mystore.com/",
                "resolved_url": "https://www.mystore.com/",
            },
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.config["vtex_host_store"], "https://www.mystore.com/")
        self.assertEqual(result.config["channels"]["wwc"]["channel_data"], {"x": 1})

    def test_url_redirected_skips_when_resolved_url_missing(self):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=URL_REDIRECTED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com/",
            data={"original_url": "https://mystore.com/"},
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertNotIn("vtex_host_store", result.config or {})
        self.connect_service.update_project_config.assert_not_called()

    def test_url_redirected_skips_connect_when_no_project_linked(self):
        self.onboarding.project = None
        self.onboarding.save()

        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=URL_REDIRECTED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com/",
            data={
                "original_url": "https://mystore.com/",
                "resolved_url": "https://www.mystore.com/",
            },
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.config["vtex_host_store"], "https://www.mystore.com/")
        self.connect_service.update_project_config.assert_not_called()

    def test_url_redirected_swallows_connect_failure(self):
        self.connect_service.update_project_config.side_effect = RuntimeError("boom")

        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=URL_REDIRECTED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com/",
            data={
                "original_url": "https://mystore.com/",
                "resolved_url": "https://www.mystore.com/",
            },
        )

        result = self.use_case.execute(self.onboarding_uuid, dto)

        self.assertEqual(result.config["vtex_host_store"], "https://www.mystore.com/")

    # ── Edge cases ─────────────────────────────────────────────────

    def test_raises_not_found_for_unknown_onboarding_uuid(self):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=10,
        )

        with self.assertRaises(ProjectOnboarding.DoesNotExist):
            self.use_case.execute(str(uuid4()), dto)
