from unittest.mock import ANY, patch

from django.conf import settings
from django.test import TestCase, override_settings

from retail.vtex.tasks import task_process_back_in_stock_notification
from retail.webhooks.vtex.usecases.dto import ProcessBackInStockNotificationDTO
from retail.webhooks.vtex.usecases.exceptions import BackInStockSendNotReadyError


USE_CASE_PATH = "retail.vtex.tasks.ProcessBackInStockNotificationUseCase"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "task-process-back-in-stock-tests",
        }
    }
)
class TaskProcessBackInStockNotificationTest(TestCase):
    @patch(USE_CASE_PATH)
    def test_delegates_to_use_case(self, mock_use_case_cls):
        task_process_back_in_stock_notification(
            account="gaboulstore",
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            locale="pt-BR",
        )

        mock_use_case_cls.from_vtex_account.assert_called_once_with(
            "gaboulstore", exec_logger=ANY
        )
        mock_use_case_cls.from_vtex_account.return_value.execute.assert_called_once_with(
            ProcessBackInStockNotificationDTO(
                sku_id="9",
                phone="5511999887766",
                name="Maria Silva",
                locale="pt-BR",
            )
        )

    @patch(USE_CASE_PATH)
    def test_propagates_send_failure_for_worker_retry(self, mock_use_case_cls):
        mock_use_case_cls.from_vtex_account.return_value.execute.side_effect = (
            BackInStockSendNotReadyError("send failed")
        )

        with self.assertRaises(BackInStockSendNotReadyError):
            task_process_back_in_stock_notification(
                account="gaboulstore",
                sku_id="9",
                phone="5511999887766",
            )

    def test_routes_to_back_in_stock_queue(self):
        self.assertEqual(
            settings.CELERY_TASK_ROUTES["task_process_back_in_stock_notification"][
                "queue"
            ],
            settings.BACK_IN_STOCK_CELERY_QUEUE,
        )
        self.assertEqual(settings.BACK_IN_STOCK_CELERY_QUEUE, "back-in-stock")
