from unittest.mock import patch

from django.test import TestCase

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.save_background_failure import (
    SaveBackgroundFailureUseCase,
)


class TestSaveBackgroundFailureUseCase(TestCase):
    def setUp(self):
        with patch("retail.projects.tasks.task_activate_agentic_cx_script"):
            self.onboarding = ProjectOnboarding.objects.create(
                vtex_account="mystore",
                completed=True,
                config={"channels": {"wwc": {}}},
            )

    def test_writes_background_error_snapshot(self):
        SaveBackgroundFailureUseCase.execute(
            "mystore", "nexus_upload", "Nexus returned 500"
        )

        self.onboarding.refresh_from_db()
        snapshot = self.onboarding.config["background_error"]
        self.assertEqual(snapshot["stage"], "nexus_upload")
        self.assertEqual(snapshot["error"], "Nexus returned 500")
        self.assertIn("timestamp", snapshot)

    def test_preserves_existing_config_keys(self):
        SaveBackgroundFailureUseCase.execute("mystore", "crawl", "timeout")

        self.onboarding.refresh_from_db()
        self.assertIn("background_error", self.onboarding.config)
        self.assertIn("channels", self.onboarding.config)

    def test_overwrites_previous_background_error(self):
        SaveBackgroundFailureUseCase.execute("mystore", "crawl", "first")
        SaveBackgroundFailureUseCase.execute("mystore", "nexus_upload", "second")

        self.onboarding.refresh_from_db()
        snapshot = self.onboarding.config["background_error"]
        self.assertEqual(snapshot["stage"], "nexus_upload")
        self.assertEqual(snapshot["error"], "second")

    def test_does_not_flip_onboarding_failed(self):
        SaveBackgroundFailureUseCase.execute("mystore", "crawl", "timeout")

        self.onboarding.refresh_from_db()
        self.assertFalse(self.onboarding.failed)
        self.assertTrue(self.onboarding.completed)

    def test_swallows_when_onboarding_does_not_exist(self):
        SaveBackgroundFailureUseCase.execute("unknown-store", "crawl", "timeout")

    @patch("retail.projects.usecases.save_background_failure.ProjectOnboarding")
    def test_swallows_unexpected_exception(self, mock_model):
        mock_model.objects.get.side_effect = RuntimeError("db down")

        SaveBackgroundFailureUseCase.execute("mystore", "crawl", "timeout")
