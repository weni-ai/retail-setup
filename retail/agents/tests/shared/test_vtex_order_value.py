from decimal import Decimal
from unittest.mock import MagicMock

from django.test import TestCase

from retail.agents.shared.vtex_order_value import (
    OrderAmountDetails,
    apply_order_amount_details,
    fetch_order_amount_details,
    parse_order_amount_details,
    propagate_order_amount_to_execution_log,
)


class ParseOrderAmountDetailsTest(TestCase):
    def test_returns_none_when_order_details_missing(self):
        self.assertEqual(
            parse_order_amount_details(None),
            OrderAmountDetails(amount=None, currency=None),
        )

    def test_converts_cents_to_major_units(self):
        details = parse_order_amount_details(
            {
                "value": 2047,
                "storePreferencesData": {"currencyCode": "BRL"},
            }
        )
        self.assertEqual(details.amount, Decimal("20.47"))
        self.assertEqual(details.currency, "BRL")

    def test_returns_currency_without_amount_when_value_missing(self):
        details = parse_order_amount_details(
            {"storePreferencesData": {"currencyCode": "MXN"}}
        )
        self.assertIsNone(details.amount)
        self.assertEqual(details.currency, "MXN")

    def test_returns_none_amount_for_invalid_value(self):
        details = parse_order_amount_details({"value": "not-a-number"})
        self.assertIsNone(details.amount)


class FetchOrderAmountDetailsTest(TestCase):
    def test_returns_empty_details_when_order_id_missing(self):
        service = MagicMock()
        details = fetch_order_amount_details(
            service, order_id=None, vtex_account="store"
        )
        self.assertEqual(details, OrderAmountDetails(amount=None, currency=None))
        service.get_order_details_by_id.assert_not_called()

    def test_fetches_and_parses_order_details(self):
        service = MagicMock()
        service.get_order_details_by_id.return_value = {
            "value": 15000,
            "storePreferencesData": {"currencyCode": "BRL"},
        }
        details = fetch_order_amount_details(
            service, order_id="order-1", vtex_account="store"
        )
        self.assertEqual(details.amount, Decimal("150.00"))
        self.assertEqual(details.currency, "BRL")
        service.get_order_details_by_id.assert_called_once_with(
            account_domain="store.myvtex.com",
            vtex_account="store",
            order_id="order-1",
        )

    def test_returns_empty_details_when_lookup_raises(self):
        service = MagicMock()
        service.get_order_details_by_id.side_effect = Exception("boom")
        details = fetch_order_amount_details(
            service, order_id="order-1", vtex_account="store"
        )
        self.assertEqual(details, OrderAmountDetails(amount=None, currency=None))


class ApplyOrderAmountDetailsTest(TestCase):
    def test_updates_execution_log_when_amount_or_currency_present(self):
        exec_logger = MagicMock()
        apply_order_amount_details(
            exec_logger,
            OrderAmountDetails(amount=Decimal("75.50"), currency="BRL"),
        )
        exec_logger.update_order_info.assert_called_once_with(
            amount=Decimal("75.50"),
            currency="BRL",
        )

    def test_updates_execution_log_with_currency_only(self):
        exec_logger = MagicMock()
        apply_order_amount_details(
            exec_logger,
            OrderAmountDetails(amount=None, currency="MXN"),
        )
        exec_logger.update_order_info.assert_called_once_with(
            amount=None,
            currency="MXN",
        )

    def test_skips_update_when_details_are_empty(self):
        exec_logger = MagicMock()
        apply_order_amount_details(
            exec_logger,
            OrderAmountDetails(amount=None, currency=None),
        )
        exec_logger.update_order_info.assert_not_called()


class PropagateOrderAmountToExecutionLogTest(TestCase):
    def test_updates_execution_log_when_amount_present(self):
        exec_logger = MagicMock()
        service = MagicMock()
        service.get_order_details_by_id.return_value = {
            "value": 3598,
            "storePreferencesData": {"currencyCode": "BRL"},
        }

        details = propagate_order_amount_to_execution_log(
            exec_logger,
            service,
            order_id="order-1",
            vtex_account="store",
        )

        self.assertEqual(details.amount, Decimal("35.98"))
        exec_logger.update_order_info.assert_called_once_with(
            amount=Decimal("35.98"),
            currency="BRL",
        )

    def test_skips_update_when_lookup_returns_no_data(self):
        exec_logger = MagicMock()
        service = MagicMock()
        service.get_order_details_by_id.return_value = {}

        propagate_order_amount_to_execution_log(
            exec_logger,
            service,
            order_id="order-1",
            vtex_account="store",
        )

        exec_logger.update_order_info.assert_not_called()
