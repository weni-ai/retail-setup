import uuid
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    PURCHASED_ORDER_STATUSES,
    CartAbandonmentService,
)


class FilterInvoicedOrdersTests(TestCase):
    """Unit tests for the pure ``_filter_invoiced_orders`` helper."""

    def test_purchased_statuses_constant_only_contains_invoiced(self):
        """Guard against accidentally widening the purchased set.

        Only ``invoiced`` is a confirmed purchase in VTEX; other statuses
        (created, payment-approved, ready-for-handling, canceled, ...)
        are intermediate or terminal-negative.
        """
        self.assertEqual(PURCHASED_ORDER_STATUSES, frozenset({"invoiced"}))

    def test_returns_only_invoiced_orders(self):
        recent_orders = [
            {"orderId": "order-1", "status": "order-created"},
            {"orderId": "order-2", "status": "payment-approved"},
            {"orderId": "order-3", "status": "invoiced"},
            {"orderId": "order-4", "status": "canceled"},
            {"orderId": "order-5", "status": "ready-for-handling"},
        ]

        result = CartAbandonmentService._filter_invoiced_orders(recent_orders)

        self.assertEqual(result, [{"orderId": "order-3", "status": "invoiced"}])

    def test_returns_empty_when_no_invoiced_status(self):
        recent_orders = [
            {"orderId": "order-1", "status": "order-created"},
            {"orderId": "order-2", "status": "canceled"},
        ]

        result = CartAbandonmentService._filter_invoiced_orders(recent_orders)

        self.assertEqual(result, [])

    def test_orders_without_status_are_filtered_out(self):
        recent_orders = [
            {"orderId": "order-1"},
            {"orderId": "order-2", "status": None},
            {"orderId": "order-3", "status": "invoiced"},
        ]

        result = CartAbandonmentService._filter_invoiced_orders(recent_orders)

        self.assertEqual(result, [{"orderId": "order-3", "status": "invoiced"}])

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(CartAbandonmentService._filter_invoiced_orders([]), [])


class EvaluateOrdersStatusFilteringTests(TestCase):
    """
    Behavioural tests for ``CartAbandonmentService._evaluate_orders``.

    Focus: a cart must only be marked as ``purchased`` when at least one
    recent order with status ``invoiced`` contains items that overlap
    with the cart. Non-invoiced orders (created, payment-approved,
    canceled, ...) must NOT block the abandoned cart notification.
    """

    def setUp(self):
        self.feature = Feature.objects.create(
            can_vtex_integrate=True, code="abandoned_cart"
        )
        self.user = User.objects.create()
        self.project = Project.objects.create(
            uuid=uuid.uuid4(), vtex_account="test-account"
        )
        self.integrated_feature = IntegratedFeature.objects.create(
            feature=self.feature,
            project=self.project,
            user=self.user,
            config={},
        )
        self.cart = Cart.objects.create(
            order_form_id="order-form-1",
            phone_number="5511999999999",
            project=self.project,
            integrated_feature=self.integrated_feature,
            config={
                "client_profile": {"email": "buyer@example.com"},
                "cart_items": [{"id": "sku-1", "quantity": 1, "price": 1000}],
                "locale": "pt-BR",
            },
        )

        self.service = CartAbandonmentService()
        self.service.vtex_io_service = MagicMock()
        # Avoid touching the cache layer / DB for project domain lookups.
        self.service._get_account_domain = MagicMock(return_value="test.myvtex.com")

    def _build_order_form(self):
        return {
            "items": [{"id": "sku-1", "quantity": 1, "price": 1000}],
            "clientProfileData": {"email": "buyer@example.com"},
            "clientPreferencesData": {"locale": "pt-BR"},
        }

    def _build_order_details(self, order_id, items):
        return {
            "orderId": order_id,
            "orderFormId": f"of-{order_id}",
            "status": "invoiced",
            "itemMetadata": {"Items": items},
        }

    def test_only_non_invoiced_orders_marks_cart_as_abandoned(self):
        """If all recent orders are not invoiced, cart must be notified."""
        orders = {
            "list": [
                {"orderId": "order-1", "status": "order-created"},
                {"orderId": "order-2", "status": "canceled"},
                {"orderId": "order-3", "status": "payment-approved"},
            ]
        }

        with patch.object(
            self.service, "_mark_cart_as_abandoned"
        ) as mock_mark_abandoned, patch.object(
            self.service,
            "_check_recent_purchases_for_cart_items",
        ) as mock_check_purchases:
            self.service._evaluate_orders(
                cart=self.cart,
                orders=orders,
                order_form=self._build_order_form(),
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_feature,
            )

        mock_check_purchases.assert_not_called()
        mock_mark_abandoned.assert_called_once()
        # The cart must NOT be marked as purchased.
        self.cart.refresh_from_db()
        self.assertNotEqual(self.cart.status, "purchased")

    def test_invoiced_order_with_matching_item_marks_cart_as_purchased(self):
        """An invoiced order containing a cart item must short-circuit notification."""
        orders = {
            "list": [
                {"orderId": "order-1", "status": "order-created"},
                {"orderId": "order-2", "status": "invoiced"},
            ]
        }

        # The detailed call returns matching items for the invoiced order only.
        self.service.vtex_io_service.get_order_details_by_id.side_effect = (
            lambda account_domain, vtex_account, order_id: self._build_order_details(
                order_id, [{"Id": "sku-1"}]
            )
        )

        with patch.object(self.service, "_mark_cart_as_abandoned") as mock_mark:
            self.service._evaluate_orders(
                cart=self.cart,
                orders=orders,
                order_form=self._build_order_form(),
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_feature,
            )

        mock_mark.assert_not_called()
        # Only the invoiced order should have been fetched (the created one
        # must not even reach get_order_details_by_id).
        self.service.vtex_io_service.get_order_details_by_id.assert_called_once_with(
            account_domain="test.myvtex.com",
            vtex_account="test-account",
            order_id="order-2",
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "purchased")

    def test_invoiced_order_without_matching_item_marks_cart_as_abandoned(self):
        orders = {
            "list": [
                {"orderId": "order-1", "status": "invoiced"},
            ]
        }
        self.service.vtex_io_service.get_order_details_by_id.return_value = (
            self._build_order_details("order-1", [{"Id": "sku-other"}])
        )

        with patch.object(self.service, "_mark_cart_as_abandoned") as mock_mark:
            self.service._evaluate_orders(
                cart=self.cart,
                orders=orders,
                order_form=self._build_order_form(),
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_feature,
            )

        mock_mark.assert_called_once()
        self.cart.refresh_from_db()
        self.assertNotEqual(self.cart.status, "purchased")

    def test_recent_orders_checked_persists_status(self):
        """The auditing payload stored in cart.config must include the status."""
        orders = {
            "list": [
                {"orderId": "order-1", "status": "invoiced"},
            ]
        }
        self.service.vtex_io_service.get_order_details_by_id.return_value = (
            self._build_order_details("order-1", [{"Id": "sku-other"}])
        )

        with patch.object(self.service, "_mark_cart_as_abandoned"):
            self.service._evaluate_orders(
                cart=self.cart,
                orders=orders,
                order_form=self._build_order_form(),
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_feature,
            )

        self.cart.refresh_from_db()
        recent_orders_checked = self.cart.config.get("recent_orders_checked", [])
        self.assertEqual(len(recent_orders_checked), 1)
        self.assertEqual(recent_orders_checked[0]["orderId"], "order-1")
        self.assertEqual(recent_orders_checked[0]["status"], "invoiced")
