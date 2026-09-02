import uuid
from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.clients.exceptions import CustomAPIException
from retail.projects.models import Project
from retail.vtex.models import BackInStockWaiter
from retail.vtex.tests.fake_redis import FakeRedis
from retail.vtex.waiting_skus import WaitingSkusIndex
from retail.webhooks.vtex.usecases.exceptions import BackInStockStockCheckError
from retail.webhooks.vtex.usecases.process_back_in_stock_stock_change import (
    ProcessBackInStockStockChangeUseCase,
    _item_availability,
    _notify_task,
    _sum_inventory,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "process-back-in-stock-stock-change-tests",
        }
    },
    BACK_IN_STOCK_NOTIFY_CELERY_QUEUE="back-in-stock-notify",
)
class ProcessBackInStockStockChangeUseCaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Store",
            vtex_account="gaboulstore",
        )
        self.redis = FakeRedis()
        self.index = WaitingSkusIndex(redis_client=self.redis)
        self.index.sadd_waiting_sku("gaboulstore", "9")
        self.mock_vtex = MagicMock()
        self.mock_notify = MagicMock()
        self.mock_agent_lookup = MagicMock()
        self.mock_agent_lookup.get_project_by_vtex_account.side_effect = (
            BaseAgentWebhookUseCase().get_project_by_vtex_account
        )
        self.mock_agent_lookup.get_integrated_agent_if_exists.return_value = MagicMock()
        self.use_case = ProcessBackInStockStockChangeUseCase(
            vtex_io_service=self.mock_vtex,
            index=self.index,
            notify_task=self.mock_notify,
            agent_lookup=self.mock_agent_lookup,
        )
        self.maria = self._waiter(phone="5511999887766", seller="1", sales_channel="1")
        self.joao = self._waiter(phone="5511888776655", seller="2", sales_channel="2")

    def tearDown(self):
        cache.clear()

    def _waiter(self, **kwargs) -> BackInStockWaiter:
        defaults = {
            "project": self.project,
            "sku_id": "9",
            "phone": "5511999887766",
            "name": "Shopper",
            "seller": "1",
            "sales_channel": "1",
        }
        defaults.update(kwargs)
        return BackInStockWaiter.objects.create(**defaults)

    def test_srems_stale_sku_when_no_pending_waiters(self):
        BackInStockWaiter.objects.all().delete()

        self.use_case.execute("gaboulstore", "9")

        self.assertNotIn(
            "9", self.redis.sets.get(self.index.key_for("gaboulstore"), set())
        )
        self.mock_vtex.proxy_vtex.assert_not_called()
        self.mock_notify.apply_async.assert_not_called()

    def test_does_not_enqueue_error_waiters(self):
        self.maria.status = BackInStockWaiter.STATUS_ERROR
        self.maria.save(update_fields=["status"])

        def proxy(**kwargs):
            if kwargs["path"].startswith("/api/logistics"):
                return {"balance": [{"availableQuantity": 5}]}
            return {"items": [{"availability": "available"}]}

        self.mock_vtex.proxy_vtex.side_effect = proxy

        self.use_case.execute("gaboulstore", "9")

        queued = [
            call.kwargs["kwargs"]["waiter_uuid"]
            for call in self.mock_notify.apply_async.call_args_list
        ]
        self.assertEqual(queued, [str(self.joao.uuid)])

    def test_skips_vtex_and_keeps_pending_when_agent_inactive(self):
        self.mock_agent_lookup.get_integrated_agent_if_exists.return_value = None

        self.use_case.execute("gaboulstore", "9")

        self.mock_vtex.proxy_vtex.assert_not_called()
        self.mock_notify.apply_async.assert_not_called()
        self.assertIn("9", self.redis.sets[self.index.key_for("gaboulstore")])
        self.assertEqual(
            BackInStockWaiter.objects.filter(
                status=BackInStockWaiter.STATUS_PENDING
            ).count(),
            2,
        )

    def test_returns_without_notify_or_srem_when_inventory_is_zero(self):
        self.mock_vtex.proxy_vtex.return_value = {
            "balance": [{"availableQuantity": 0, "totalQuantity": 0}]
        }

        self.use_case.execute("gaboulstore", "9")

        self.mock_notify.apply_async.assert_not_called()
        self.assertIn("9", self.redis.sets[self.index.key_for("gaboulstore")])
        self.assertEqual(
            BackInStockWaiter.objects.filter(
                status=BackInStockWaiter.STATUS_PENDING
            ).count(),
            2,
        )

    def test_notifies_only_store_one_when_store_two_is_without_stock(self):
        def proxy(**kwargs):
            path = kwargs["path"]
            if path.startswith("/api/logistics"):
                return {"balance": [{"availableQuantity": 5}]}
            seller = kwargs["data"]["items"][0]["seller"]
            if seller == "1":
                return {"items": [{"availability": "available"}]}
            return {"items": [{"availability": "withoutStock"}]}

        self.mock_vtex.proxy_vtex.side_effect = proxy

        self.use_case.execute("gaboulstore", "9")

        queued = [
            call.kwargs["kwargs"]["waiter_uuid"]
            for call in self.mock_notify.apply_async.call_args_list
        ]
        self.assertEqual(queued, [str(self.maria.uuid)])
        self.assertEqual(
            self.mock_notify.apply_async.call_args.kwargs["queue"],
            "back-in-stock-notify",
        )
        self.assertIn("9", self.redis.sets[self.index.key_for("gaboulstore")])
        self.joao.refresh_from_db()
        self.assertEqual(self.joao.status, BackInStockWaiter.STATUS_PENDING)

    def test_cannot_be_delivered_is_treated_as_available(self):
        BackInStockWaiter.objects.filter(pk=self.joao.pk).delete()

        def proxy(**kwargs):
            if kwargs["path"].startswith("/api/logistics"):
                return {"balance": [{"availableQuantity": 1}]}
            return {"items": [{"availability": "cannotBeDelivered"}]}

        self.mock_vtex.proxy_vtex.side_effect = proxy

        self.use_case.execute("gaboulstore", "9")

        self.assertEqual(self.mock_notify.apply_async.call_count, 1)

    def test_caches_simulation_per_seller_and_channel(self):
        self._waiter(phone="5511777665544", seller="1", sales_channel="1")

        def proxy(**kwargs):
            if kwargs["path"].startswith("/api/logistics"):
                return {"balance": [{"availableQuantity": 3}]}
            return {"items": [{"availability": "available"}]}

        self.mock_vtex.proxy_vtex.side_effect = proxy

        self.use_case.execute("gaboulstore", "9")

        checkout_calls = [
            call
            for call in self.mock_vtex.proxy_vtex.call_args_list
            if call.kwargs["path"] == "/api/checkout/pub/orderForms/simulation"
        ]
        self.assertEqual(len(checkout_calls), 2)

    def test_raises_when_vtex_check_fails(self):
        self.mock_vtex.proxy_vtex.side_effect = CustomAPIException(
            status_code=500, detail="down"
        )

        with self.assertRaises(BackInStockStockCheckError):
            self.use_case.execute("gaboulstore", "9")

    def test_skips_when_project_is_missing(self):
        self.use_case.execute("unknown", "9")

        self.mock_vtex.proxy_vtex.assert_not_called()
        self.mock_notify.apply_async.assert_not_called()

    def test_reuses_cached_project_on_second_stock_change(self):
        self.mock_vtex.proxy_vtex.return_value = {
            "balance": [{"availableQuantity": 0, "totalQuantity": 0}]
        }
        self.use_case.execute("gaboulstore", "9")

        with patch.object(Project.objects, "get") as mock_get:
            self.use_case.execute("gaboulstore", "9")
            mock_get.assert_not_called()

    def test_inventory_helpers_cover_edge_payloads(self):
        self.assertEqual(_sum_inventory("bad"), 0)
        self.assertEqual(
            _sum_inventory({"balance": ["x", {"hasUnlimitedQuantity": True}]}), 1
        )
        self.assertEqual(_sum_inventory({"balance": [{"totalQuantity": 4}]}), 4)
        self.assertEqual(_item_availability("bad"), "withoutStock")
        self.assertEqual(_item_availability({"items": []}), "withoutStock")
        self.assertEqual(_item_availability({"items": ["x"]}), "withoutStock")

    def test_lazy_notify_task_is_the_celery_task(self):
        from retail.vtex.tasks import task_notify_back_in_stock_waiter

        self.assertIs(_notify_task(), task_notify_back_in_stock_waiter)
