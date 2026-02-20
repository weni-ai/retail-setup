from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_dto import CrawlerWebhookDTO
from retail.projects.usecases.update_onboarding_progress import (
    COMPLETED_EVENT,
    FAILED_EVENT,
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
            current_step="CRAWL",
        )
        self.project_uuid = str(self.project.uuid)

    # ── Progress handling ──────────────────────────────────────────

    def test_updates_progress_on_generic_event(self):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=35,
        )

        result = UpdateOnboardingProgressUseCase.execute(self.project_uuid, dto)

        self.assertEqual(result.progress, 35)

    def test_does_not_decrease_progress(self):
        """Multi-threaded crawler may send out-of-order events."""
        self.onboarding.progress = 50
        self.onboarding.save()

        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=49,
        )

        result = UpdateOnboardingProgressUseCase.execute(self.project_uuid, dto)

        self.assertEqual(result.progress, 50)

    def test_increases_progress(self):
        self.onboarding.progress = 30
        self.onboarding.save()

        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=60,
        )

        result = UpdateOnboardingProgressUseCase.execute(self.project_uuid, dto)

        self.assertEqual(result.progress, 60)

    # ── Completed event ────────────────────────────────────────────

    @patch("retail.projects.usecases.update_onboarding_progress.task_configure_nexus")
    @patch(
        "retail.projects.usecases.update_onboarding_progress.acquire_task_lock",
        return_value=True,
    )
    def test_completed_sets_progress_100_and_dispatches_task(
        self, mock_lock, mock_task
    ):
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

        result = UpdateOnboardingProgressUseCase.execute(self.project_uuid, dto)

        self.assertEqual(result.progress, 100)
        self.assertEqual(result.crawler_result, ProjectOnboarding.SUCCESS)
        mock_lock.assert_called_once_with("configure_nexus", "mystore")
        mock_task.delay.assert_called_once_with("mystore", contents)

    @patch("retail.projects.usecases.update_onboarding_progress.task_configure_nexus")
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

        result = UpdateOnboardingProgressUseCase.execute(self.project_uuid, dto)

        self.assertEqual(result.progress, 100)
        self.assertEqual(result.crawler_result, ProjectOnboarding.SUCCESS)
        mock_task.delay.assert_not_called()

    # ── Failed event ───────────────────────────────────────────────

    def test_handles_failed_event(self):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event=FAILED_EVENT,
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=0,
            data={"error": "Connection timeout"},
        )

        result = UpdateOnboardingProgressUseCase.execute(self.project_uuid, dto)

        self.assertEqual(result.crawler_result, ProjectOnboarding.FAIL)

    # ── Edge cases ─────────────────────────────────────────────────

    def test_raises_not_found_for_unknown_project_uuid(self):
        dto = CrawlerWebhookDTO(
            task_id="task-1",
            event="crawl.subpage.progress",
            timestamp="2026-01-01T00:00:00Z",
            url="https://mystore.com.br/",
            progress=10,
        )

        with self.assertRaises(ProjectOnboarding.DoesNotExist):
            UpdateOnboardingProgressUseCase.execute(str(uuid4()), dto)
