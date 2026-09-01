from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from retail.webhooks.vtex.usecases.dto import (
    EnqueueBackInStockNotificationsDTO,
    ProcessBackInStockNotificationDTO,
)
from retail.webhooks.vtex.usecases.enqueue_back_in_stock_notifications import (
    EnqueueBackInStockNotificationsUseCase,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "enqueue-back-in-stock-notifications-tests",
        }
    },
    BACK_IN_STOCK_CELERY_QUEUE="back-in-stock",
)
class EnqueueBackInStockNotificationsUseCaseTest(TestCase):
    def setUp(self):
        self.mock_task = MagicMock()
        self.use_case = EnqueueBackInStockNotificationsUseCase(
            process_task=self.mock_task
        )

    def test_queues_one_task_per_shopper_in_fifo_order(self):
        dto = EnqueueBackInStockNotificationsDTO(
            account="gaboulstore",
            shoppers=(
                ProcessBackInStockNotificationDTO(
                    sku_id="9",
                    phone="5511999887766",
                    name="Maria Silva",
                    locale="pt-BR",
                ),
                ProcessBackInStockNotificationDTO(
                    sku_id="9",
                    phone="5511888776655",
                    name="João Santos",
                    locale="pt-BR",
                ),
            ),
        )

        self.use_case.execute(dto)

        queued = [
            call.kwargs["kwargs"] for call in self.mock_task.apply_async.call_args_list
        ]
        self.assertEqual(
            queued,
            [
                {
                    "account": "gaboulstore",
                    "sku_id": "9",
                    "phone": "5511999887766",
                    "name": "Maria Silva",
                    "locale": "pt-BR",
                },
                {
                    "account": "gaboulstore",
                    "sku_id": "9",
                    "phone": "5511888776655",
                    "name": "João Santos",
                    "locale": "pt-BR",
                },
            ],
        )
        for call in self.mock_task.apply_async.call_args_list:
            self.assertEqual(call.kwargs["queue"], "back-in-stock")

    def test_logs_batch_size_without_phone(self):
        dto = EnqueueBackInStockNotificationsDTO(
            account="gaboulstore",
            shoppers=(
                ProcessBackInStockNotificationDTO(
                    sku_id="9",
                    phone="5511999887766",
                    name="Maria Silva",
                    locale="pt-BR",
                ),
            ),
        )

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.enqueue_back_in_stock_notifications",
            level="INFO",
        ) as logs:
            self.use_case.execute(dto)

        combined = " ".join(logs.output)
        self.assertIn("shoppers=1", combined)
        self.assertIn("sku_id=9", combined)
        self.assertNotIn("5511999887766", combined)

    def test_stops_and_logs_when_broker_fails_mid_batch(self):
        dto = EnqueueBackInStockNotificationsDTO(
            account="gaboulstore",
            shoppers=(
                ProcessBackInStockNotificationDTO(
                    sku_id="9",
                    phone="5511999887766",
                    name="Maria Silva",
                    locale="pt-BR",
                ),
                ProcessBackInStockNotificationDTO(
                    sku_id="9",
                    phone="5511888776655",
                    name="João Santos",
                    locale="pt-BR",
                ),
            ),
        )
        self.mock_task.apply_async.side_effect = [None, RuntimeError("broker down")]

        with self.assertLogs(
            "retail.webhooks.vtex.usecases.enqueue_back_in_stock_notifications",
            level="ERROR",
        ) as logs:
            with self.assertRaises(RuntimeError):
                self.use_case.execute(dto)

        self.assertEqual(self.mock_task.apply_async.call_count, 2)
        combined = " ".join(logs.output)
        self.assertIn("queued=1", combined)
        self.assertIn("remaining=1", combined)
        self.assertNotIn("5511888776655", combined)
