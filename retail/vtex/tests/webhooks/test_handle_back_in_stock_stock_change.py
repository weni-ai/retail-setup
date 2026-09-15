from unittest.mock import MagicMock

from django.test import SimpleTestCase, override_settings

from retail.vtex.tests.fake_redis import FakeRedis
from retail.vtex.waiting_skus import WaitingSkusIndex
from retail.webhooks.vtex.usecases.dto import BackInStockStockChangeDTO
from retail.webhooks.vtex.usecases.handle_back_in_stock_stock_change import (
    SKU_NOT_WAITING,
    HandleBackInStockStockChangeUseCase,
)


@override_settings(BACK_IN_STOCK_STOCK_CHANGE_CELERY_QUEUE="back-in-stock-stock-change")
class HandleBackInStockStockChangeUseCaseTest(SimpleTestCase):
    def setUp(self):
        self.redis = FakeRedis()
        self.index = WaitingSkusIndex(redis_client=self.redis)
        self.mock_task = MagicMock()
        self.mock_rebuild = MagicMock()
        self.use_case = HandleBackInStockStockChangeUseCase(
            index=self.index,
            rebuild_use_case=self.mock_rebuild,
            stock_change_task=self.mock_task,
        )

    def test_skips_when_sku_not_in_set(self):
        self.index.rebuild_for_account("gaboulstore", ["12"])

        result = self.use_case.execute(
            BackInStockStockChangeDTO(account="gaboulstore", sku_id="9")
        )

        self.assertEqual(
            result.to_dict(), {"accepted": False, "reason": SKU_NOT_WAITING}
        )
        self.mock_task.apply_async.assert_not_called()

    def test_enqueues_stock_change_queue_when_sku_is_waiting(self):
        self.index.rebuild_for_account("gaboulstore", ["9"])

        result = self.use_case.execute(
            BackInStockStockChangeDTO(account="gaboulstore", sku_id="9")
        )

        self.assertEqual(result.to_dict(), {"accepted": True})
        self.mock_task.apply_async.assert_called_once_with(
            kwargs={"account": "gaboulstore", "sku_id": "9"},
            queue="back-in-stock-stock-change",
        )

    def test_missing_key_rebuilds_and_accepts_real_pending_sku(self):
        def rebuild(account):
            self.index.rebuild_for_account(account, ["9"])

        self.mock_rebuild.execute_for_account.side_effect = rebuild

        result = self.use_case.execute(
            BackInStockStockChangeDTO(account="gaboulstore", sku_id="9")
        )

        self.mock_rebuild.execute_for_account.assert_called_once_with("gaboulstore")
        self.assertTrue(result.accepted)

    def test_missing_key_rebuild_without_pending_is_not_waiting(self):
        self.mock_rebuild.execute_for_account.side_effect = lambda account: None

        result = self.use_case.execute(
            BackInStockStockChangeDTO(account="gaboulstore", sku_id="9")
        )

        self.assertEqual(result.reason, SKU_NOT_WAITING)
        self.mock_task.apply_async.assert_not_called()

    def test_lazy_stock_change_task_is_the_celery_task(self):
        from retail.vtex.tasks import task_process_back_in_stock_stock_change
        from retail.webhooks.vtex.usecases.handle_back_in_stock_stock_change import (
            _stock_change_task,
        )

        self.assertIs(_stock_change_task(), task_process_back_in_stock_stock_change)
