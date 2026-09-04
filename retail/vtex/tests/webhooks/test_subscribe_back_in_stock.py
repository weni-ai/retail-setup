import uuid

from django.core.cache import cache
from django.db import IntegrityError
from unittest.mock import patch

from django.test import TestCase, override_settings

from retail.projects.models import Project
from retail.vtex.models import BackInStockWaiter
from retail.vtex.tests.fake_redis import FakeRedis
from retail.vtex.waiting_skus import WAITING_SKUS_TTL_SECONDS, WaitingSkusIndex
from retail.webhooks.vtex.usecases.dto import SubscribeBackInStockDTO
from retail.webhooks.vtex.usecases.exceptions import ProjectNotFoundError
from retail.webhooks.vtex.usecases.subscribe_back_in_stock import (
    SubscribeBackInStockUseCase,
)


def _dto(**overrides) -> SubscribeBackInStockDTO:
    payload = {
        "account": "gaboulstore",
        "sku_id": "9",
        "phone": "5511999887766",
        "name": "Maria Silva",
        "seller": "1",
        "sales_channel": "1",
        "locale": "pt-BR",
    }
    payload.update(overrides)
    return SubscribeBackInStockDTO(**payload)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "subscribe-back-in-stock-tests",
        }
    }
)
class SubscribeBackInStockUseCaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Store",
            vtex_account="gaboulstore",
        )
        self.redis = FakeRedis()
        self.index = WaitingSkusIndex(redis_client=self.redis)
        self.use_case = SubscribeBackInStockUseCase(index=self.index)

    def tearDown(self):
        cache.clear()

    def test_persists_waiter_and_sadds_new_sku_with_ttl(self):
        self.use_case.execute(_dto())

        waiter = BackInStockWaiter.objects.get()
        self.assertEqual(waiter.sku_id, "9")
        self.assertEqual(waiter.phone, "5511999887766")
        self.assertEqual(waiter.seller, "1")
        self.assertEqual(waiter.status, BackInStockWaiter.STATUS_PENDING)
        key = self.index.key_for("gaboulstore")
        self.assertEqual(self.redis.sets[key], {"9"})
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_duplicate_pending_does_not_insert_again(self):
        self.use_case.execute(_dto())
        self.use_case.execute(_dto(name="Maria 2"))

        self.assertEqual(BackInStockWaiter.objects.count(), 1)
        self.assertEqual(BackInStockWaiter.objects.get().name, "Maria Silva")

    def test_second_phone_same_sku_inserts_waiter_and_renews_ttl(self):
        self.use_case.execute(_dto())
        key = self.index.key_for("gaboulstore")
        self.redis.ttls[key] = 50_000

        self.use_case.execute(_dto(phone="5511888776655", name="João Santos"))

        self.assertEqual(BackInStockWaiter.objects.count(), 2)
        self.assertEqual(self.redis.sets[key], {"9"})
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_new_sku_is_added_and_ttl_is_renewed(self):
        self.use_case.execute(_dto())
        key = self.index.key_for("gaboulstore")
        self.redis.ttls[key] = 50_000

        self.use_case.execute(_dto(sku_id="12", phone="5511777665544"))

        self.assertEqual(self.redis.sets[key], {"9", "12"})
        self.assertEqual(self.redis.ttls[key], WAITING_SKUS_TTL_SECONDS)

    def test_reopens_sent_waiter_to_pending(self):
        waiter = BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            seller="1",
            sales_channel="1",
            status=BackInStockWaiter.STATUS_SENT,
        )

        self.use_case.execute(_dto())

        waiter.refresh_from_db()
        self.assertEqual(waiter.status, BackInStockWaiter.STATUS_PENDING)
        self.assertIsNone(waiter.sent_at)
        self.assertEqual(BackInStockWaiter.objects.count(), 1)

    def test_reopens_error_waiter_to_pending(self):
        waiter = BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            seller="1",
            sales_channel="1",
            status=BackInStockWaiter.STATUS_ERROR,
            error_details=[{"code": "send_failed", "message": "old"}],
        )

        self.use_case.execute(_dto())

        waiter.refresh_from_db()
        self.assertEqual(waiter.status, BackInStockWaiter.STATUS_PENDING)
        self.assertEqual(waiter.error_details, [])
        self.assertEqual(BackInStockWaiter.objects.count(), 1)

    def test_raises_when_project_missing(self):
        with self.assertRaises(ProjectNotFoundError):
            self.use_case.execute(_dto(account="unknown"))

        self.assertEqual(BackInStockWaiter.objects.count(), 0)

    def test_raises_when_multiple_projects_share_account(self):
        with patch.object(
            Project.objects,
            "get",
            side_effect=Project.MultipleObjectsReturned(),
        ):
            with self.assertRaises(ProjectNotFoundError):
                self.use_case.execute(_dto())

    def test_recovers_from_integrity_error_on_concurrent_insert(self):
        existing = BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            seller="1",
            sales_channel="1",
        )
        with patch.object(
            BackInStockWaiter.objects,
            "get_or_create",
            side_effect=IntegrityError(),
        ):
            self.use_case.execute(_dto())

        self.assertEqual(BackInStockWaiter.objects.get().uuid, existing.uuid)

    def test_reuses_cached_project_on_second_subscribe(self):
        self.use_case.execute(_dto())

        with patch.object(Project.objects, "get") as mock_get:
            self.use_case.execute(_dto(phone="5511888776655", name="João Santos"))
            mock_get.assert_not_called()

    def test_ignores_body_account_when_dto_account_is_claim(self):
        self.use_case.execute(_dto(account="gaboulstore"))

        self.assertEqual(
            BackInStockWaiter.objects.get().project.vtex_account, "gaboulstore"
        )
