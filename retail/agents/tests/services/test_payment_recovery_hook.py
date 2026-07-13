from django.test import SimpleTestCase

from retail.agents.domains.agent_integration.services.payment_recovery_hook import (
    DEFAULT_SALES_CHANNELS,
    build_payment_recovery_hook_expression,
    build_payment_recovery_hook_payload,
    build_sales_channel_clause,
)


class BuildSalesChannelClauseTest(SimpleTestCase):
    def test_returns_none_for_empty_list(self):
        self.assertIsNone(build_sales_channel_clause([]))

    def test_single_channel(self):
        self.assertEqual(
            build_sales_channel_clause(["1"]),
            '(salesChannel = "1")',
        )

    def test_multiple_channels(self):
        self.assertEqual(
            build_sales_channel_clause(["1", "2"]),
            '(salesChannel = "1" or salesChannel = "2")',
        )


class BuildPaymentRecoveryHookExpressionTest(SimpleTestCase):
    def test_default_sales_channel_expression(self):
        expression = build_payment_recovery_hook_expression(DEFAULT_SALES_CHANNELS)
        self.assertEqual(
            expression,
            'isCompleted = false and (salesChannel = "1") '
            'and paymentData.transactions.payments[paymentSystem = "125"]',
        )

    def test_empty_sales_channels_matches_all_channels_expression(self):
        expression = build_payment_recovery_hook_expression([])
        self.assertEqual(
            expression,
            "isCompleted = false and "
            'paymentData.transactions.payments[paymentSystem = "125"]',
        )
        self.assertNotIn("salesChannel", expression)
        self.assertIn("isCompleted = false", expression)

    def test_multiple_sales_channels(self):
        expression = build_payment_recovery_hook_expression(["1", "2"])
        self.assertEqual(
            expression,
            "isCompleted = false and "
            '(salesChannel = "1" or salesChannel = "2") and '
            'paymentData.transactions.payments[paymentSystem = "125"]',
        )


class BuildPaymentRecoveryHookPayloadTest(SimpleTestCase):
    def test_builds_complete_payload(self):
        payload = build_payment_recovery_hook_payload(
            "https://example.com/webhook/",
            ["2"],
        )

        self.assertEqual(payload["filter"]["type"], "FromOrders")
        self.assertEqual(
            payload["filter"]["expression"],
            'isCompleted = false and (salesChannel = "2") '
            'and paymentData.transactions.payments[paymentSystem = "125"]',
        )
        self.assertFalse(payload["filter"]["disableSingleFire"])
        self.assertEqual(payload["hook"]["url"], "https://example.com/webhook/")
        self.assertEqual(
            payload["hook"]["headers"],
            {"User-Agent": "vtex-retail/0.0.0"},
        )

    def test_defaults_to_channel_one_when_sales_channels_omitted(self):
        payload = build_payment_recovery_hook_payload("https://example.com/webhook/")
        self.assertIn('salesChannel = "1"', payload["filter"]["expression"])
