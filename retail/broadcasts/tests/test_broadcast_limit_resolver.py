from unittest.mock import MagicMock

from uuid import uuid4

from django.test import TestCase, override_settings

from retail.broadcasts.services.broadcast_limit_resolver import (
    BroadcastLimitResolver,
)
from retail.projects.models import Project


class BroadcastLimitResolverTest(TestCase):
    def setUp(self):
        self.trial_status_service = MagicMock()
        self.trial_status_service.is_trial_active.return_value = True
        self.resolver = BroadcastLimitResolver(
            trial_status_service=self.trial_status_service
        )
        self.project = Project.objects.create(name="Project A", uuid=uuid4())

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_falls_back_to_global_setting_when_no_override(self):
        self.assertEqual(self.resolver.resolve(self.project), 1000)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_project_override_takes_precedence(self):
        self.project.config = {"trial_broadcast_limit": 250}
        self.project.save(update_fields=["config"])

        self.assertEqual(self.resolver.resolve(self.project), 250)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_accepts_numeric_string(self):
        self.project.config = {"trial_broadcast_limit": "500"}
        self.project.save(update_fields=["config"])

        self.assertEqual(self.resolver.resolve(self.project), 500)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_invalid_value_falls_back_to_default(self):
        self.project.config = {"trial_broadcast_limit": "not-a-number"}
        self.project.save(update_fields=["config"])

        self.assertEqual(self.resolver.resolve(self.project), 1000)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_non_positive_value_falls_back_to_default(self):
        self.project.config = {"trial_broadcast_limit": 0}
        self.project.save(update_fields=["config"])

        self.assertEqual(self.resolver.resolve(self.project), 1000)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=0)
    def test_returns_none_when_no_override_and_default_disabled(self):
        self.assertIsNone(self.resolver.resolve(self.project))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=0)
    def test_uses_override_even_when_default_disabled(self):
        self.project.config = {"trial_broadcast_limit": 50}
        self.project.save(update_fields=["config"])

        self.assertEqual(self.resolver.resolve(self.project), 50)

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_returns_none_when_project_is_not_in_trial(self):
        self.trial_status_service.is_trial_active.return_value = False

        self.assertIsNone(self.resolver.resolve(self.project))

    @override_settings(RETAIL_TRIAL_BROADCAST_LIMIT=1000)
    def test_project_override_is_ignored_when_not_in_trial(self):
        self.trial_status_service.is_trial_active.return_value = False
        self.project.config = {"trial_broadcast_limit": 50}
        self.project.save(update_fields=["config"])

        self.assertIsNone(self.resolver.resolve(self.project))
