import uuid
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from retail.projects.models import Project
from retail.vtex.models import BackInStockWaiter
from retail.vtex.usecases.cleanup_back_in_stock_subscriptions import (
    SENT_WAITER_RETENTION_DAYS,
    CleanupBackInStockSubscriptionsUseCase,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cleanup-back-in-stock-subscriptions-tests",
        }
    }
)
class CleanupBackInStockSubscriptionsUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Store",
            vtex_account="gaboulstore",
        )
        self.use_case = CleanupBackInStockSubscriptionsUseCase()

    def _waiter(self, **kwargs) -> BackInStockWaiter:
        defaults = {
            "project": self.project,
            "sku_id": "9",
            "phone": "5511999887766",
            "name": "Maria",
            "seller": "1",
            "sales_channel": "1",
        }
        defaults.update(kwargs)
        return BackInStockWaiter.objects.create(**defaults)

    def test_sent_retention_is_thirty_days(self):
        self.assertEqual(SENT_WAITER_RETENTION_DAYS, 30)

    def test_deletes_old_sent_waiters_and_keeps_pending(self):
        old_sent = self._waiter(
            phone="5511999887766", status=BackInStockWaiter.STATUS_SENT
        )
        recent_sent = self._waiter(
            phone="5511888776655", status=BackInStockWaiter.STATUS_SENT
        )
        pending = self._waiter(phone="5511777665544")
        stale = timezone.now() - timedelta(days=SENT_WAITER_RETENTION_DAYS + 1)
        BackInStockWaiter.objects.filter(pk=old_sent.pk).update(
            sent_at=stale, created_at=stale
        )
        BackInStockWaiter.objects.filter(pk=recent_sent.pk).update(
            sent_at=timezone.now()
        )

        self.use_case.execute()

        remaining = set(BackInStockWaiter.objects.values_list("phone", flat=True))
        self.assertEqual(remaining, {recent_sent.phone, pending.phone})
        self.assertFalse(BackInStockWaiter.objects.filter(pk=old_sent.pk).exists())

    def test_keeps_old_error_waiters(self):
        error = self._waiter(
            phone="5511666554433",
            status=BackInStockWaiter.STATUS_ERROR,
            error_details=[{"code": "send_failed", "message": "old"}],
        )
        stale = timezone.now() - timedelta(days=SENT_WAITER_RETENTION_DAYS + 1)
        BackInStockWaiter.objects.filter(pk=error.pk).update(created_at=stale)

        self.use_case.execute()

        self.assertTrue(BackInStockWaiter.objects.filter(pk=error.pk).exists())
