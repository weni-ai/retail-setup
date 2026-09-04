import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings

from retail.projects.models import Project
from retail.vtex.models import BackInStockWaiter
from retail.vtex.tests.fake_redis import FakeRedis
from retail.vtex.waiting_skus import WAITING_SKUS_TTL_SECONDS, WaitingSkusIndex
from retail.webhooks.vtex.usecases.rebuild_back_in_stock_waiting_skus import (
    RebuildBackInStockWaitingSkusUseCase,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "rebuild-back-in-stock-waiting-skus-tests",
        }
    }
)
class RebuildBackInStockWaitingSkusUseCaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Store",
            vtex_account="gaboulstore",
        )
        self.other = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Other",
            vtex_account="otherstore",
        )
        self.redis = FakeRedis()
        self.index = WaitingSkusIndex(redis_client=self.redis)
        self.use_case = RebuildBackInStockWaitingSkusUseCase(index=self.index)

    def tearDown(self):
        cache.clear()

    def test_rebuilds_distinct_pending_skus_and_drops_orphans(self):
        BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511999887766",
            name="Maria",
            seller="1",
            sales_channel="1",
        )
        BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511888776655",
            name="João",
            seller="2",
            sales_channel="2",
        )
        BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="12",
            phone="5511777665544",
            name="Ana",
            seller="1",
            sales_channel="1",
            status=BackInStockWaiter.STATUS_SENT,
        )
        key = self.index.key_for("gaboulstore")
        self.redis.sets[key] = {"orphan", "12"}
        self.redis.ttls[key] = 10

        self.use_case.execute()

        self.assertEqual(self.redis.sets[key], {"9"})
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_restores_sku_missing_from_set_when_pending_exists(self):
        BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511999887766",
            name="Maria",
            seller="1",
            sales_channel="1",
        )

        self.use_case.execute_for_account("gaboulstore")

        self.assertEqual(self.redis.sets[self.index.key_for("gaboulstore")], {"9"})

    def test_does_not_rebuild_accounts_without_pending(self):
        BackInStockWaiter.objects.create(
            project=self.other,
            sku_id="1",
            phone="5511999887766",
            name="Maria",
            seller="1",
            sales_channel="1",
            status=BackInStockWaiter.STATUS_SENT,
        )
        other_key = self.index.key_for("otherstore")
        self.redis.sets[other_key] = {"1"}
        self.redis.ttls[other_key] = 10

        self.use_case.execute()

        self.assertEqual(self.redis.sets[other_key], {"1"})

    def test_unknown_account_clears_set(self):
        key = self.index.key_for("missing")
        self.redis.sets[key] = {"9"}
        self.redis.ttls[key] = 10

        self.use_case.execute_for_account("missing")

        self.assertNotIn(key, self.redis.sets)
