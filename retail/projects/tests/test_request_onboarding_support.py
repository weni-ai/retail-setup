from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project, ProjectOnboarding
from retail.projects.usecases.onboarding_dto import RequestOnboardingSupportDTO
from retail.projects.usecases.request_onboarding_support import (
    RequestOnboardingSupportUseCase,
)


class TestRequestOnboardingSupportUseCase(TestCase):
    def setUp(self):
        self.notification = MagicMock()
        self.use_case = RequestOnboardingSupportUseCase(
            notification_service=self.notification
        )

    def test_dispatches_notification_with_full_snapshot_when_onboarding_exists(self):
        project = Project.objects.create(
            name="My Store", uuid=uuid4(), vtex_account="mystore"
        )
        onboarding = ProjectOnboarding.objects.create(
            vtex_account="mystore",
            project=project,
            current_step="CRAWL",
            current_page="setup_channel",
            progress=42,
            failed=True,
            crawler_result=ProjectOnboarding.FAIL,
            config={
                "reason_failed": "Crawler offline",
                "channels": {"wpp-cloud": {"app_uuid": "abc"}},
            },
        )

        dto = RequestOnboardingSupportDTO(
            vtex_account="mystore",
            data={"message": "stuck on channel setup"},
        )
        self.use_case.execute(dto)

        self.notification.notify.assert_called_once()
        kwargs = self.notification.notify.call_args.kwargs
        self.assertEqual(kwargs["vtex_account"], "mystore")
        self.assertEqual(kwargs["data"], {"message": "stuck on channel setup"})

        snapshot = kwargs["onboarding"]
        self.assertEqual(snapshot["uuid"], str(onboarding.uuid))
        self.assertEqual(snapshot["project_name"], "My Store")
        self.assertEqual(snapshot["project_uuid"], str(project.uuid))
        self.assertEqual(snapshot["current_step"], "CRAWL")
        self.assertEqual(snapshot["current_page"], "setup_channel")
        self.assertEqual(snapshot["progress"], 42)
        self.assertTrue(snapshot["failed"])
        self.assertFalse(snapshot["completed"])
        self.assertFalse(snapshot["skipped"])
        self.assertEqual(snapshot["crawler_result"], ProjectOnboarding.FAIL)
        self.assertIsNotNone(snapshot["created_on"])
        self.assertEqual(snapshot["config"]["reason_failed"], "Crawler offline")
        self.assertIn("channels", snapshot["config"])

    def test_dispatches_notification_with_none_snapshot_when_onboarding_missing(self):
        dto = RequestOnboardingSupportDTO(
            vtex_account="ghoststore",
            data={"any": "thing"},
        )

        self.use_case.execute(dto)

        self.notification.notify.assert_called_once()
        kwargs = self.notification.notify.call_args.kwargs
        self.assertEqual(kwargs["vtex_account"], "ghoststore")
        self.assertEqual(kwargs["data"], {"any": "thing"})
        self.assertIsNone(kwargs["onboarding"])

    def test_handles_onboarding_without_project_linked(self):
        ProjectOnboarding.objects.create(
            vtex_account="mystore",
            current_step="CHANNEL_SETUP",
            progress=15,
        )

        dto = RequestOnboardingSupportDTO(vtex_account="mystore", data={})
        self.use_case.execute(dto)

        snapshot = self.notification.notify.call_args.kwargs["onboarding"]
        self.assertEqual(snapshot["current_step"], "CHANNEL_SETUP")
        self.assertEqual(snapshot["progress"], 15)
        self.assertIsNone(snapshot["project_name"])
        self.assertIsNone(snapshot["project_uuid"])
        self.assertEqual(snapshot["config"], {})
