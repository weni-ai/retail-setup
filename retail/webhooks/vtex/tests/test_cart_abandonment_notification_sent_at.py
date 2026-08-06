from datetime import datetime, timezone as dt_timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    CartAbandonmentService,
)


class CartAbandonmentServiceNotificationSentAtTest(TestCase):
    """Guards that ``_update_cart_status`` populates ``notification_sent_at``
    only when the cart transitions to ``delivered_success`` so the abandoned
    cart conversion lookup has a reliable timestamp to compare against the
    VTEX order ``creationDate``.
    """

    def setUp(self):
        self.project = Project.objects.create(
            name="Notification Timestamp Project",
            uuid=uuid4(),
            vtex_account="testaccount",
        )
        self.cart = Cart.objects.create(
            phone_number="5511999999999",
            project=self.project,
            order_form_id="order-form-1",
        )
        self.service = CartAbandonmentService.__new__(CartAbandonmentService)

    @patch("retail.webhooks.vtex.services_cart_abandonment_unified.timezone.now")
    def test_delivered_success_sets_notification_sent_at(self, mock_now):
        fixed_now = datetime(2026, 5, 1, 10, 0, 0, tzinfo=dt_timezone.utc)
        mock_now.return_value = fixed_now

        self.service._update_cart_status(self.cart, "delivered_success")

        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "delivered_success")
        self.assertEqual(self.cart.notification_sent_at, fixed_now)

    def test_other_status_does_not_set_notification_sent_at(self):
        self.service._update_cart_status(self.cart, "delivered_error", response="boom")

        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "delivered_error")
        self.assertIsNone(self.cart.notification_sent_at)

    def test_abandoned_status_does_not_set_notification_sent_at(self):
        self.service._update_cart_status(self.cart, "abandoned")

        self.cart.refresh_from_db()
        self.assertTrue(self.cart.abandoned)
        self.assertIsNone(self.cart.notification_sent_at)

    def test_delivered_error_records_error_message(self):
        response = MagicMock()
        response.__str__ = lambda self: "broadcast-failure-payload"

        self.service._update_cart_status(
            self.cart, "delivered_error", response=response
        )

        self.cart.refresh_from_db()
        self.assertIn("broadcast-failure-payload", self.cart.error_message)
