import uuid
from unittest.mock import MagicMock

from django.test import TestCase, override_settings

from retail.vtex.models import BackInStockWaiter
from retail.projects.models import Project
from retail.vtex.tests.fake_redis import FakeRedis
from retail.vtex.waiting_skus import WaitingSkusIndex
from retail.webhooks.vtex.usecases.dto import ProcessBackInStockNotificationResult
from retail.webhooks.vtex.usecases.exceptions import BackInStockSendNotReadyError
from retail.webhooks.vtex.usecases.notify_back_in_stock_waiter import (
    ERROR_SEND_FAILED,
    NotifyBackInStockWaiterUseCase,
)
from retail.webhooks.vtex.usecases.process_back_in_stock_notification import (
    NOTIFICATION_SENT,
)


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "notify-back-in-stock-waiter-tests",
        }
    }
)
class NotifyBackInStockWaiterUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Store",
            vtex_account="gaboulstore",
        )
        self.redis = FakeRedis()
        self.index = WaitingSkusIndex(redis_client=self.redis)
        self.index.sadd_waiting_sku("gaboulstore", "9")
        self.mock_send = MagicMock()
        self.mock_send.execute.return_value = ProcessBackInStockNotificationResult(
            discarded=False, reason=NOTIFICATION_SENT
        )
        self.use_case = NotifyBackInStockWaiterUseCase(
            index=self.index, send_use_case=self.mock_send
        )
        self.maria = BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511999887766",
            name="Maria Silva",
            seller="1",
            sales_channel="1",
        )

    def _execute(self, waiter: BackInStockWaiter) -> None:
        self.use_case.execute(
            account="gaboulstore",
            waiter_uuid=str(waiter.uuid),
            sku_id=waiter.sku_id,
            phone=waiter.phone,
            name=waiter.name,
            locale=waiter.locale,
            seller=waiter.seller,
            sales_channel=waiter.sales_channel,
        )

    def test_forwards_offer_fields_to_send_use_case(self):
        self._execute(self.maria)

        dto = self.mock_send.execute.call_args[0][0]
        self.assertEqual(dto.seller, "1")
        self.assertEqual(dto.sales_channel, "1")

    def test_marks_sent_and_srems_when_last_pending_for_sku(self):
        self._execute(self.maria)

        self.maria.refresh_from_db()
        self.assertEqual(self.maria.status, BackInStockWaiter.STATUS_SENT)
        self.assertIsNotNone(self.maria.sent_at)
        self.assertNotIn(
            "9", self.redis.sets.get(self.index.key_for("gaboulstore"), set())
        )

    def test_keeps_sku_in_set_when_another_store_is_still_pending(self):
        BackInStockWaiter.objects.create(
            project=self.project,
            sku_id="9",
            phone="5511888776655",
            name="João Santos",
            seller="2",
            sales_channel="2",
        )

        self._execute(self.maria)

        self.maria.refresh_from_db()
        self.assertEqual(self.maria.status, BackInStockWaiter.STATUS_SENT)
        self.assertIn("9", self.redis.sets[self.index.key_for("gaboulstore")])

    def test_does_not_send_again_when_already_sent(self):
        self.maria.status = BackInStockWaiter.STATUS_SENT
        self.maria.save(update_fields=["status"])

        self._execute(self.maria)

        self.mock_send.execute.assert_not_called()

    def test_skips_invalid_waiter_uuid(self):
        self.use_case.execute(
            account="gaboulstore",
            waiter_uuid="not-a-uuid",
            sku_id="9",
            phone="5511999887766",
            name="Maria",
            locale="pt-BR",
            seller="1",
            sales_channel="1",
        )

        self.mock_send.execute.assert_not_called()

    def test_keeps_pending_when_agent_is_inactive(self):
        self.mock_send.execute.return_value = ProcessBackInStockNotificationResult(
            discarded=True, reason="Agent is not active for this account."
        )

        self._execute(self.maria)

        self.maria.refresh_from_db()
        self.assertEqual(self.maria.status, BackInStockWaiter.STATUS_PENDING)
        self.assertEqual(self.maria.error_details, [])
        self.assertIn("9", self.redis.sets[self.index.key_for("gaboulstore")])

    def test_marks_error_and_reraises_when_send_fails(self):
        self.mock_send.execute.side_effect = BackInStockSendNotReadyError("send failed")

        with self.assertRaises(BackInStockSendNotReadyError):
            self._execute(self.maria)

        self.maria.refresh_from_db()
        self.assertEqual(self.maria.status, BackInStockWaiter.STATUS_ERROR)
        self.assertEqual(self.maria.error_details[0]["code"], ERROR_SEND_FAILED)
        self.assertEqual(self.maria.error_details[0]["message"], "send failed")

    def test_retries_error_waiter_and_clears_details_on_success(self):
        self.maria.status = BackInStockWaiter.STATUS_ERROR
        self.maria.error_details = [{"code": ERROR_SEND_FAILED, "message": "old"}]
        self.maria.save(update_fields=["status", "error_details"])
        self.index.sadd_waiting_sku("gaboulstore", "9")

        self._execute(self.maria)

        self.maria.refresh_from_db()
        self.assertEqual(self.maria.status, BackInStockWaiter.STATUS_SENT)
        self.assertEqual(self.maria.error_details, [])

    def test_does_not_overwrite_row_another_worker_already_marked_sent(self):
        BackInStockWaiter.objects.filter(pk=self.maria.pk).update(
            status=BackInStockWaiter.STATUS_SENT
        )

        self.use_case._mark_sent(self.maria)
        self.use_case._mark_error(self.maria, ERROR_SEND_FAILED, "late")

        self.maria.refresh_from_db()
        self.assertEqual(self.maria.status, BackInStockWaiter.STATUS_SENT)
        self.assertEqual(self.maria.error_details, [])
