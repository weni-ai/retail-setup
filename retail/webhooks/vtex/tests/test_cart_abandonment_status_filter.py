import uuid
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth.models import User
from django.test import TestCase

from retail.features.models import Feature, IntegratedFeature
from retail.projects.models import Project
from retail.vtex.models import Cart
from retail.webhooks.vtex.services_cart_abandonment_unified import (
    OMS_LIST_MAX_PAGES,
    OMS_LIST_ORDERS_PATH,
    OMS_LIST_PAGE_SIZE,
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

    def _iso(self, delta: timedelta) -> str:
        return (self.cart.created_on + delta).isoformat()

    def _build_order_details(self, order_id, items, creation_date=None):
        details = {
            "orderId": order_id,
            "orderFormId": f"of-{order_id}",
            "status": "invoiced",
            "itemMetadata": {"Items": items},
        }
        if creation_date is not None:
            details["creationDate"] = creation_date
        return details

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

    def test_invoiced_order_before_cart_creation_does_not_mark_purchased(self):
        """SKU overlap on an order older than the cart must not block the send.

        Reproduces the gigavc false positive: a 2025 invoiced order sharing
        the cart SKU was treated as a conversion of a later orderForm.
        """
        old_creation = self._iso(timedelta(days=-365))
        orders = {
            "list": [
                {
                    "orderId": "order-2025",
                    "status": "invoiced",
                    "creationDate": old_creation,
                }
            ]
        }
        self.service.vtex_io_service.get_order_details_by_id.return_value = (
            self._build_order_details(
                "order-2025", [{"Id": "sku-1"}], creation_date=old_creation
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

        mock_mark.assert_called_once()
        self.service.vtex_io_service.get_order_details_by_id.assert_not_called()
        self.cart.refresh_from_db()
        self.assertNotEqual(self.cart.status, "purchased")

    def test_invoiced_order_after_cart_creation_with_matching_sku_marks_purchased(
        self,
    ):
        """A matching invoiced order placed after the cart must still block."""
        new_creation = self._iso(timedelta(hours=2))
        orders = {
            "list": [
                {
                    "orderId": "order-new",
                    "status": "invoiced",
                    "creationDate": new_creation,
                }
            ]
        }
        self.service.vtex_io_service.get_order_details_by_id.return_value = (
            self._build_order_details(
                "order-new", [{"Id": "sku-1"}], creation_date=new_creation
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
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "purchased")

    def test_date_filter_runs_before_recent_orders_window(self):
        """Pre-cart invoiced orders must not hide a later matching purchase.

        Five invoiced orders older than the cart plus one post-cart
        matching order must still mark the cart as purchased.
        """
        old_creation = self._iso(timedelta(days=-200))
        new_creation = self._iso(timedelta(hours=3))
        older_orders = [
            {
                "orderId": f"order-old-{index}",
                "status": "invoiced",
                "creationDate": old_creation,
            }
            for index in range(5)
        ]
        orders = {
            "list": older_orders
            + [
                {
                    "orderId": "order-new",
                    "status": "invoiced",
                    "creationDate": new_creation,
                }
            ]
        }
        self.service.vtex_io_service.get_order_details_by_id.return_value = (
            self._build_order_details(
                "order-new", [{"Id": "sku-1"}], creation_date=new_creation
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
        self.service.vtex_io_service.get_order_details_by_id.assert_called_once_with(
            account_domain="test.myvtex.com",
            vtex_account="test-account",
            order_id="order-new",
        )
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "purchased")

    def test_details_creation_date_before_cart_skips_sku_match(self):
        """List items without a date still drop out when details are older."""
        old_creation = self._iso(timedelta(days=-365))
        orders = {
            "list": [
                {"orderId": "order-undated", "status": "invoiced"},
            ]
        }
        self.service.vtex_io_service.get_order_details_by_id.return_value = (
            self._build_order_details(
                "order-undated", [{"Id": "sku-1"}], creation_date=old_creation
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

        mock_mark.assert_called_once()
        self.cart.refresh_from_db()
        self.assertNotEqual(self.cart.status, "purchased")
        recent_orders_checked = self.cart.config.get("recent_orders_checked", [])
        self.assertEqual(recent_orders_checked[0]["creationDate"], old_creation)


class FilterOrdersCreatedAfterCartTests(TestCase):
    """Unit tests for the local creationDate cut."""

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
            config={},
        )
        self.service = CartAbandonmentService()

    def test_drops_orders_created_before_the_cart(self):
        older = (self.cart.created_on - timedelta(days=10)).isoformat()
        newer = (self.cart.created_on + timedelta(hours=1)).isoformat()
        orders = [
            {"orderId": "old", "creationDate": older},
            {"orderId": "new", "creationDate": newer},
            {"orderId": "undated"},
        ]

        kept = self.service._filter_orders_created_after_cart(orders, self.cart)

        self.assertEqual(
            [order["orderId"] for order in kept],
            ["new", "undated"],
        )

    def test_parse_vtex_datetime_accepts_z_suffix_and_extra_fraction(self):
        parsed = CartAbandonmentService._parse_vtex_datetime(
            "2025-03-15T12:30:00.1234567Z"
        )

        self.assertIsNotNone(parsed)
        self.assertEqual(parsed.year, 2025)
        self.assertEqual(parsed.month, 3)
        self.assertEqual(parsed.day, 15)
        self.assertIsNotNone(parsed.tzinfo)

    def test_parse_vtex_datetime_returns_none_for_invalid_values(self):
        self.assertIsNone(CartAbandonmentService._parse_vtex_datetime(None))
        self.assertIsNone(CartAbandonmentService._parse_vtex_datetime(""))
        self.assertIsNone(CartAbandonmentService._parse_vtex_datetime("not-a-date"))
        self.assertIsNone(CartAbandonmentService._parse_vtex_datetime(123))

    def test_to_oms_utc_converts_naive_datetime_to_utc_zulu(self):
        naive = datetime(2026, 8, 24, 12, 30, 45, 123456)
        self.assertEqual(
            CartAbandonmentService._to_oms_utc(naive),
            "2026-08-24T12:30:45.000Z",
        )

    def test_oms_total_pages_defaults_to_one_when_paging_missing(self):
        self.assertEqual(CartAbandonmentService._oms_total_pages({}), 1)
        self.assertEqual(
            CartAbandonmentService._oms_total_pages({"paging": {"pages": "x"}}),
            1,
        )
        self.assertEqual(
            CartAbandonmentService._oms_total_pages({"paging": {"pages": 3}}),
            3,
        )


class FetchOrdersPlacedAfterCartTests(TestCase):
    """OMS list via ``proxy_vtex``: date filter, pagination, no SKU on list."""

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
            config={"cart_items": [{"id": "sku-1"}]},
        )
        self.service = CartAbandonmentService()
        self.service.vtex_io_service = MagicMock()
        self.service._get_account_domain = MagicMock(return_value="test.myvtex.com")

    def test_proxy_query_filters_by_email_and_creation_date(self):
        self.service.vtex_io_service.proxy_vtex.return_value = {
            "list": [],
            "paging": {"pages": 1},
        }

        result = self.service._fetch_orders_placed_after_cart(
            self.cart, "buyer@example.com"
        )

        self.assertEqual(result, {"list": []})
        self.service.vtex_io_service.proxy_vtex.assert_called_once()
        kwargs = self.service.vtex_io_service.proxy_vtex.call_args.kwargs
        self.assertEqual(kwargs["method"], "GET")
        self.assertEqual(kwargs["path"], OMS_LIST_ORDERS_PATH)
        self.assertEqual(kwargs["account_domain"], "test.myvtex.com")
        self.assertEqual(kwargs["vtex_account"], "test-account")
        params = kwargs["params"]
        self.assertEqual(params["q"], "buyer@example.com")
        self.assertEqual(params["orderBy"], "creationDate,desc")
        self.assertEqual(params["page"], "1")
        self.assertEqual(params["per_page"], str(OMS_LIST_PAGE_SIZE))
        date_from = CartAbandonmentService._to_oms_utc(self.cart.created_on)
        self.assertTrue(
            params["f_creationDate"].startswith(f"creationDate:[{date_from} TO ")
        )
        self.assertTrue(params["f_creationDate"].endswith("]"))
        self.assertNotIn("%", params["f_creationDate"])

    def test_paginates_until_last_page(self):
        self.service.vtex_io_service.proxy_vtex.side_effect = [
            {
                "list": [{"orderId": "order-1", "status": "invoiced"}],
                "paging": {"pages": 2},
            },
            {
                "list": [{"orderId": "order-2", "status": "invoiced"}],
                "paging": {"pages": 2},
            },
        ]

        result = self.service._fetch_orders_placed_after_cart(
            self.cart, "buyer@example.com"
        )

        self.assertEqual(
            [order["orderId"] for order in result["list"]],
            ["order-1", "order-2"],
        )
        self.assertEqual(self.service.vtex_io_service.proxy_vtex.call_count, 2)
        pages = [
            call.kwargs["params"]["page"]
            for call in self.service.vtex_io_service.proxy_vtex.call_args_list
        ]
        self.assertEqual(pages, ["1", "2"])

    def test_stops_at_oms_page_cap(self):
        self.service.vtex_io_service.proxy_vtex.return_value = {
            "list": [{"orderId": "order-x"}],
            "paging": {"pages": OMS_LIST_MAX_PAGES + 5},
        }

        result = self.service._fetch_orders_placed_after_cart(
            self.cart, "buyer@example.com"
        )

        self.assertEqual(
            self.service.vtex_io_service.proxy_vtex.call_count, OMS_LIST_MAX_PAGES
        )
        self.assertEqual(len(result["list"]), OMS_LIST_MAX_PAGES)

    def test_matching_sku_on_items_id_marks_purchased(self):
        """Prefer ``items[].id`` over itemMetadata when both are present."""
        new_creation = (self.cart.created_on + timedelta(hours=1)).isoformat()
        orders = {
            "list": [
                {
                    "orderId": "order-new",
                    "status": "invoiced",
                    "creationDate": new_creation,
                }
            ]
        }
        self.service.vtex_io_service.get_order_details_by_id.return_value = {
            "orderId": "order-new",
            "orderFormId": "of-order-new",
            "status": "invoiced",
            "creationDate": new_creation,
            "items": [{"id": "sku-1"}],
            "itemMetadata": {"Items": [{"Id": "sku-other"}]},
        }

        with patch.object(self.service, "_mark_cart_as_abandoned") as mock_mark:
            self.service._evaluate_orders(
                cart=self.cart,
                orders=orders,
                order_form={"items": [{"id": "sku-1"}]},
                client_profile={"email": "buyer@example.com"},
                integration_config=self.integrated_feature,
            )

        mock_mark.assert_not_called()
        self.cart.refresh_from_db()
        self.assertEqual(self.cart.status, "purchased")

    def test_extract_order_sku_ids_falls_back_to_item_metadata(self):
        sku_ids = CartAbandonmentService._extract_order_sku_ids(
            {"itemMetadata": {"Items": [{"Id": "sku-meta"}]}}
        )
        self.assertEqual(sku_ids, {"sku-meta"})
