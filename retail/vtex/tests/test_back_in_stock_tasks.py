from unittest.mock import ANY, patch

from django.conf import settings
from django.test import TestCase, override_settings

from retail.vtex.tasks import (
    task_notify_back_in_stock_waiter,
    task_process_back_in_stock_stock_change,
    task_rebuild_back_in_stock_waiting_skus,
)
from retail.webhooks.vtex.usecases.exceptions import BackInStockSendNotReadyError


CACHE = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "back-in-stock-task-tests",
    }
}


@override_settings(CACHES=CACHE)
class TaskProcessBackInStockStockChangeTest(TestCase):
    @patch("retail.vtex.tasks.ProcessBackInStockStockChangeUseCase")
    def test_delegates_to_use_case(self, mock_use_case_cls):
        task_process_back_in_stock_stock_change(account="gaboulstore", sku_id="9")

        mock_use_case_cls.return_value.execute.assert_called_once_with(
            account="gaboulstore", sku_id="9"
        )

    def test_routes_to_stock_change_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["task_process_back_in_stock_stock_change"][
                "queue"
            ],
            settings.BACK_IN_STOCK_STOCK_CHANGE_CELERY_QUEUE,
        )


@override_settings(CACHES=CACHE)
class TaskNotifyBackInStockWaiterTest(TestCase):
    @patch("retail.vtex.tasks.NotifyBackInStockWaiterUseCase")
    @patch("retail.vtex.tasks.ProcessBackInStockNotificationUseCase")
    def test_delegates_to_notify_use_case(self, mock_send_cls, mock_notify_cls):
        task_notify_back_in_stock_waiter(
            account="gaboulstore",
            waiter_uuid="waiter-uuid",
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            locale="pt-BR",
        )

        mock_send_cls.from_vtex_account.assert_called_once_with(
            "gaboulstore", exec_logger=ANY
        )
        mock_notify_cls.assert_called_once_with(
            send_use_case=mock_send_cls.from_vtex_account.return_value
        )
        mock_notify_cls.return_value.execute.assert_called_once_with(
            account="gaboulstore",
            waiter_uuid="waiter-uuid",
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            locale="pt-BR",
        )

    @patch("retail.vtex.tasks.NotifyBackInStockWaiterUseCase")
    @patch("retail.vtex.tasks.ProcessBackInStockNotificationUseCase")
    def test_propagates_send_failure(self, mock_send_cls, mock_notify_cls):
        mock_notify_cls.return_value.execute.side_effect = BackInStockSendNotReadyError(
            "send failed"
        )

        with self.assertRaises(BackInStockSendNotReadyError):
            task_notify_back_in_stock_waiter(
                account="gaboulstore",
                waiter_uuid="waiter-uuid",
                sku_id="9",
                phone="5511999887766",
            )

    def test_routes_to_notify_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["task_notify_back_in_stock_waiter"]["queue"],
            settings.BACK_IN_STOCK_NOTIFY_CELERY_QUEUE,
        )


@override_settings(CACHES=CACHE)
class TaskRebuildBackInStockWaitingSkusTest(TestCase):
    @patch("retail.vtex.tasks.RebuildBackInStockWaitingSkusUseCase")
    def test_delegates_to_use_case(self, mock_use_case_cls):
        task_rebuild_back_in_stock_waiting_skus()

        mock_use_case_cls.return_value.execute.assert_called_once_with()

    @patch("retail.vtex.tasks.RebuildBackInStockWaitingSkusUseCase")
    def test_swallows_unexpected_error(self, mock_use_case_cls):
        mock_use_case_cls.return_value.execute.side_effect = RuntimeError("boom")

        task_rebuild_back_in_stock_waiting_skus()

    def test_beat_schedule_is_two_am(self):
        entry = settings.CELERY_BEAT_SCHEDULE["task-rebuild-back-in-stock-waiting-skus"]
        self.assertEqual(entry["task"], "task_rebuild_back_in_stock_waiting_skus")
        self.assertEqual(entry["schedule"].hour, {2})
        self.assertEqual(entry["schedule"].minute, {0})
        self.assertNotIn("options", entry)
        self.assertNotIn(
            "task_rebuild_back_in_stock_waiting_skus",
            settings.CELERY_TASK_ROUTES,
        )
        self.assertNotEqual(
            settings.BACK_IN_STOCK_STOCK_CHANGE_CELERY_QUEUE,
            settings.BACK_IN_STOCK_NOTIFY_CELERY_QUEUE,
        )
