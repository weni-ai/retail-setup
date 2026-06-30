from django.test import TestCase

from retail.projects.models import ProjectOnboarding
from retail.projects.usecases.content_base_progress_helpers import STATUS_COMPLETE
from retail.projects.usecases.get_content_base_progress import (
    GetContentBaseProgressUseCase,
)


class TestGetContentBaseProgressUseCase(TestCase):
    def test_returns_weighted_progress_from_config(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={
                "content_base_progress": {
                    "crawl_percent": 100,
                    "upload_percent": 50,
                    "status": "uploading",
                }
            },
        )

        progress = GetContentBaseProgressUseCase().execute("mystore")

        self.assertEqual(progress, 66)

    def test_returns_zero_when_snapshot_missing(self):
        ProjectOnboarding.objects.create(vtex_account="mystore")

        progress = GetContentBaseProgressUseCase().execute("mystore")

        self.assertEqual(progress, 0)

    def test_returns_one_hundred_when_complete(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            config={
                "content_base_progress": {
                    "crawl_percent": 100,
                    "upload_percent": 100,
                    "status": STATUS_COMPLETE,
                }
            },
        )

        progress = GetContentBaseProgressUseCase().execute("mystore")

        self.assertEqual(progress, 100)

    def test_raises_when_onboarding_not_found(self):
        with self.assertRaises(ProjectOnboarding.DoesNotExist):
            GetContentBaseProgressUseCase().execute("unknown")
