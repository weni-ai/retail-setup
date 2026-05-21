"""Tests for the Direct Send payload-builder helpers (T010).

Covers ``substitute_template_variables`` (regex-based ``{{N}}``
substitution with whitespace tolerance, missing-index warning,
extra-index silent ignore) and ``is_valid_direct_send_template_name``
(Meta's snake_case + ≤ 512 chars rule — research Decision 7 /
FR-017).
"""

import logging

from django.test import TestCase

from retail.agents.domains.agent_webhook.services.direct_send_payload_builder import (
    is_valid_direct_send_template_name,
    substitute_template_variables,
)


class SubstituteTemplateVariablesTest(TestCase):
    def test_substitutes_indexed_placeholders(self):
        result = substitute_template_variables(
            "Olá {{1}}, seu pedido {{2}} foi enviado.",
            {"1": "Maria", "2": "12345"},
            template_name="weni_order_shipped",
        )
        self.assertEqual(result, "Olá Maria, seu pedido 12345 foi enviado.")

    def test_substitutes_with_whitespace_inside_braces(self):
        result = substitute_template_variables(
            "Olá {{ 1 }}, pedido {{ 2}} chegou {{3 }}.",
            {"1": "Maria", "2": "12345", "3": "hoje"},
            template_name="weni_order_shipped",
        )
        self.assertEqual(result, "Olá Maria, pedido 12345 chegou hoje.")

    def test_missing_index_substitutes_empty_string_and_logs_warning(self):
        with self.assertLogs(
            "retail.agents.domains.agent_webhook.services.direct_send_payload_builder",
            level=logging.WARNING,
        ) as captured:
            result = substitute_template_variables(
                "Olá {{1}}, seu pedido {{2}}.",
                {"1": "Maria"},
                template_name="weni_order_shipped",
            )
        self.assertEqual(result, "Olá Maria, seu pedido .")
        self.assertTrue(
            any(
                "variable_missing" in line
                and "template=weni_order_shipped" in line
                and "index=2" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_extra_index_is_silently_ignored(self):
        result = substitute_template_variables(
            "Olá {{1}}.",
            {"1": "Maria", "2": "extra", "99": "ignored"},
            template_name="weni_order_shipped",
        )
        self.assertEqual(result, "Olá Maria.")

    def test_no_placeholders_returns_input_verbatim(self):
        result = substitute_template_variables(
            "Olá cliente.",
            {"1": "ignored"},
            template_name="weni_order_shipped",
        )
        self.assertEqual(result, "Olá cliente.")

    def test_empty_text_returns_empty_text(self):
        self.assertEqual(
            substitute_template_variables(
                "", {"1": "Maria"}, template_name="weni_order_shipped"
            ),
            "",
        )

    def test_non_numeric_variable_value_coerced_to_string(self):
        result = substitute_template_variables(
            "Pedido #{{1}}.",
            {"1": 12345},
            template_name="weni_order_shipped",
        )
        self.assertEqual(result, "Pedido #12345.")


class IsValidDirectSendTemplateNameTest(TestCase):
    def test_valid_snake_case_name_passes(self):
        self.assertTrue(is_valid_direct_send_template_name("weni_order_shipped"))

    def test_valid_with_digits_passes(self):
        self.assertTrue(
            is_valid_direct_send_template_name("weni_order_shipped_1700000000")
        )

    def test_name_with_hyphen_fails(self):
        self.assertFalse(is_valid_direct_send_template_name("weni-order-shipped"))

    def test_name_with_uppercase_fails(self):
        self.assertFalse(is_valid_direct_send_template_name("Weni_Order_Shipped"))

    def test_name_with_non_ascii_fails(self):
        self.assertFalse(is_valid_direct_send_template_name("weni_pedido_enviado_ç"))

    def test_name_with_dot_fails(self):
        self.assertFalse(is_valid_direct_send_template_name("weni.order.shipped"))

    def test_empty_name_fails(self):
        self.assertFalse(is_valid_direct_send_template_name(""))

    def test_name_at_512_chars_passes(self):
        self.assertTrue(is_valid_direct_send_template_name("a" * 512))

    def test_name_over_512_chars_fails(self):
        self.assertFalse(is_valid_direct_send_template_name("a" * 513))
