from unittest.mock import patch

from django.test import TestCase, override_settings

from retail.vtex.tasks import task_cleanup_back_in_stock_subscriptions


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "task-cleanup-back-in-stock-tests",
        }
    }
)
class TaskCleanupBackInStockSubscriptionsTest(TestCase):
    @patch("retail.vtex.tasks.CleanupBackInStockSubscriptionsUseCase")
    def test_delegates_to_use_case(self, mock_use_case_cls):
        task_cleanup_back_in_stock_subscriptions()

        mock_use_case_cls.return_value.execute.assert_called_once_with()

    @patch("retail.vtex.tasks.CleanupBackInStockSubscriptionsUseCase")
    def test_swallows_unexpected_error(self, mock_use_case_cls):
        mock_use_case_cls.return_value.execute.side_effect = RuntimeError("boom")

        task_cleanup_back_in_stock_subscriptions()

    def test_beat_schedule_includes_daily_cleanup(self):
        from django.conf import settings

        self.assertIn(
            "task-cleanup-back-in-stock-subscriptions",
            settings.CELERY_BEAT_SCHEDULE,
        )
        entry = settings.CELERY_BEAT_SCHEDULE[
            "task-cleanup-back-in-stock-subscriptions"
        ]
        self.assertEqual(entry["task"], "task_cleanup_back_in_stock_subscriptions")
