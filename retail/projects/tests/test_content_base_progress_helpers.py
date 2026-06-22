from uuid import uuid4

from django.test import TestCase

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.content_base_progress_helpers import (
    STATUS_COMPLETE,
    STATUS_CRAWLING,
    STATUS_FAILED,
    STATUS_UPLOADING,
    compute_overall_percent,
    persist_content_base_progress,
)


class TestComputeOverallPercent(TestCase):
    def test_returns_zero_for_empty_snapshot(self):
        self.assertEqual(compute_overall_percent({}), 0)

    def test_returns_zero_when_not_started(self):
        snapshot = {
            "crawl_percent": 0,
            "upload_percent": 0,
            "status": "pending",
        }
        self.assertEqual(compute_overall_percent(snapshot), 0)

    def test_returns_crawl_weighted_progress(self):
        snapshot = {"crawl_percent": 50, "upload_percent": 0}
        self.assertEqual(compute_overall_percent(snapshot), 16)

    def test_returns_thirty_three_when_crawl_done_upload_not_started(self):
        snapshot = {
            "crawl_percent": 100,
            "upload_percent": 0,
            "status": STATUS_UPLOADING,
        }
        self.assertEqual(compute_overall_percent(snapshot), 33)

    def test_returns_sixty_seven_when_upload_halfway(self):
        snapshot = {"crawl_percent": 100, "upload_percent": 50}
        self.assertEqual(compute_overall_percent(snapshot), 66)

    def test_returns_one_hundred_when_complete_status(self):
        snapshot = {
            "crawl_percent": 100,
            "upload_percent": 0,
            "status": STATUS_COMPLETE,
        }
        self.assertEqual(compute_overall_percent(snapshot), 100)

    def test_returns_partial_on_failed_status(self):
        snapshot = {
            "crawl_percent": 60,
            "upload_percent": 0,
            "status": STATUS_FAILED,
        }
        self.assertEqual(compute_overall_percent(snapshot), 20)


class TestPersistContentBaseProgress(TestCase):
    def setUp(self):
        self.onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={
                "channels": {"wwc": {"app_uuid": str(uuid4())}},
                "vtex_host_store": "https://www.mystore.com/",
            },
        )

    def test_merges_without_removing_other_config_keys(self):
        persist_content_base_progress(
            self.onboarding,
            crawl_percent=35,
            status=STATUS_CRAWLING,
        )

        self.onboarding.refresh_from_db()
        self.assertEqual(
            self.onboarding.config["content_base_progress"]["crawl_percent"], 35
        )
        self.assertEqual(
            self.onboarding.config["content_base_progress"]["status"], STATUS_CRAWLING
        )
        self.assertIn("channels", self.onboarding.config)
        self.assertEqual(
            self.onboarding.config["vtex_host_store"], "https://www.mystore.com/"
        )

    def test_updates_existing_snapshot_in_place(self):
        persist_content_base_progress(
            self.onboarding,
            crawl_percent=100,
            upload_percent=0,
            status=STATUS_UPLOADING,
            total_files=2,
        )
        persist_content_base_progress(self.onboarding, upload_percent=50)

        self.onboarding.refresh_from_db()
        snapshot = self.onboarding.config["content_base_progress"]
        self.assertEqual(snapshot["crawl_percent"], 100)
        self.assertEqual(snapshot["upload_percent"], 50)
        self.assertEqual(snapshot["total_files"], 2)
