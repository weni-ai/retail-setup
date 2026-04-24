from unittest.mock import MagicMock

from uuid import uuid4

from django.test import TestCase, override_settings
from django.utils import timezone

from retail.broadcasts.models import ProjectBroadcastCounter
from retail.broadcasts.services.broadcast_limit_resolver import (
    BroadcastLimitResolver,
)
from retail.broadcasts.usecases.project_limit_guard import ProjectLimitGuard
from retail.projects.models import Project


class ProjectLimitGuardTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.counter = ProjectBroadcastCounter.objects.create(
            project=self.project, total_delivered=0
        )
        self.suspension_service = MagicMock()
        self.trial_status_service = MagicMock()
        self.trial_status_service.is_trial_active.return_value = True
        self.limit_resolver = BroadcastLimitResolver(
            trial_status_service=self.trial_status_service
        )
        self.guard = ProjectLimitGuard(
            limit_resolver=self.limit_resolver,
            suspension_service=self.suspension_service,
        )

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_should_block_returns_false_when_under_limit(self):
        self.counter.total_delivered = 100
        self.assertFalse(self.guard.should_block(self.counter))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_should_block_returns_true_when_limit_reached(self):
        self.counter.total_delivered = 1000
        self.assertTrue(self.guard.should_block(self.counter))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_should_block_returns_false_when_already_blocked(self):
        self.counter.total_delivered = 9999
        self.counter.blocked_at = timezone.now()
        self.assertFalse(self.guard.should_block(self.counter))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=0)
    def test_should_block_returns_false_when_limit_disabled(self):
        self.counter.total_delivered = 10_000
        self.assertFalse(self.guard.should_block(self.counter))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_trigger_block_marks_project_and_counter_and_invokes_suspend(self):
        self.counter.total_delivered = 1000
        self.counter.save()

        self.guard.trigger_block(self.project.pk)

        self.counter.refresh_from_db()
        self.project.refresh_from_db()
        self.assertIsNotNone(self.counter.blocked_at)
        self.assertTrue(self.project.is_blocked)
        self.suspension_service.suspend.assert_called_once_with(
            project_uuid=str(self.project.uuid), limit=1000
        )

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_trigger_block_is_idempotent_when_already_blocked(self):
        original_blocked_at = timezone.now()
        self.counter.blocked_at = original_blocked_at
        self.counter.save()
        self.project.is_blocked = True
        self.project.save()

        self.guard.trigger_block(self.project.pk)

        self.counter.refresh_from_db()
        self.assertEqual(self.counter.blocked_at, original_blocked_at)
        self.suspension_service.suspend.assert_not_called()

    def test_trigger_block_does_nothing_when_counter_missing(self):
        self.counter.delete()

        self.guard.trigger_block(self.project.pk)

        self.project.refresh_from_db()
        self.assertFalse(self.project.is_blocked)
        self.suspension_service.suspend.assert_not_called()

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_should_block_uses_project_override_when_present(self):
        self.project.config = {"trial_broadcast_limit": 50}
        self.project.save(update_fields=["config"])
        self.counter.refresh_from_db()
        self.counter.total_delivered = 50

        self.assertTrue(self.guard.should_block(self.counter))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=10)
    def test_project_override_higher_than_default_keeps_unblocked(self):
        self.project.config = {"trial_broadcast_limit": 5000}
        self.project.save(update_fields=["config"])
        self.counter.refresh_from_db()
        self.counter.total_delivered = 100

        self.assertFalse(self.guard.should_block(self.counter))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_trigger_block_passes_project_override_to_suspend(self):
        self.project.config = {"trial_broadcast_limit": 250}
        self.project.save(update_fields=["config"])
        self.counter.total_delivered = 250
        self.counter.save()

        self.guard.trigger_block(self.project.pk)

        self.suspension_service.suspend.assert_called_once_with(
            project_uuid=str(self.project.uuid), limit=250
        )

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_should_block_returns_false_when_project_is_not_in_trial(self):
        self.trial_status_service.is_trial_active.return_value = False
        self.counter.total_delivered = 9999

        self.assertFalse(self.guard.should_block(self.counter))
