"""Tests for the Direct Send payload-builder helpers. Anchor: FR-013 / FR-017."""

import logging

from django.test import TestCase

from retail.agents.domains.agent_webhook.services.direct_send_payload_builder import (
    build_direct_send_cta_message,
    build_direct_send_header,
    build_direct_send_quick_replies,
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


class BuildDirectSendHeaderEdgeCasesTest(TestCase):
    """Defensive branches of ``build_direct_send_header``.

    The dispatcher tolerates malformed metadata gracefully so the
    broadcast can be skipped without raising. Both branches are
    contract-side guarantees per ``contracts/messaging-gateway-payload.md``
    §3.2 (only IMAGE and TEXT headers are emitted; everything else is
    a no-op).
    """

    def test_image_header_without_image_url_returns_none(self):
        result = build_direct_send_header(
            {"header": {"header_type": "IMAGE", "text": "placeholder"}},
            template_variables={},
            template_name="weni_order_shipped",
            image_url=None,
        )
        self.assertIsNone(result)

    def test_unknown_header_type_returns_none(self):
        result = build_direct_send_header(
            {"header": {"header_type": "VIDEO", "text": "ignored"}},
            template_variables={},
            template_name="weni_order_shipped",
        )
        self.assertIsNone(result)


class BuildDirectSendCtaMessageTest(TestCase):
    """Helper for the ``cta_message`` sub-object. Anchor: FR-014a."""

    def test_returns_none_when_metadata_has_no_buttons(self):
        result = build_direct_send_cta_message(
            metadata={"body": "Olá"},
            template_variables={},
            template_name="weni_order_shipped",
        )
        self.assertIsNone(result)

    def test_returns_none_when_buttons_contain_no_url_entry(self):
        result = build_direct_send_cta_message(
            metadata={"buttons": [{"type": "QUICK_REPLY", "text": "Sim"}]},
            template_variables={},
            template_name="weni_order_shipped",
        )
        self.assertIsNone(result)

    def test_returns_cta_message_with_substituted_display_text_and_url(self):
        result = build_direct_send_cta_message(
            metadata={
                "buttons": [
                    {
                        "type": "URL",
                        "text": "Acomp {{1}}",
                        "url": "https://loja.com/track/{{2}}",
                    }
                ]
            },
            template_variables={"1": "Maria", "2": "12345"},
            template_name="weni_order_shipped",
        )
        self.assertEqual(
            result,
            {"display_text": "Acomp Maria", "url": "https://loja.com/track/12345"},
        )


class BuildDirectSendQuickRepliesTest(TestCase):
    """Helper for the ``quick_replies`` flat array. Anchor: FR-014b."""

    def test_returns_none_when_metadata_has_no_buttons(self):
        result = build_direct_send_quick_replies(
            metadata={"body": "Olá"},
            template_variables={},
            template_name="weni_order_shipped",
        )
        self.assertIsNone(result)

    def test_returns_none_when_buttons_contain_no_quick_reply_entry(self):
        result = build_direct_send_quick_replies(
            metadata={
                "buttons": [{"type": "URL", "text": "Acomp", "url": "https://loja.com"}]
            },
            template_variables={},
            template_name="weni_order_shipped",
        )
        self.assertIsNone(result)

    def test_returns_list_of_substituted_titles(self):
        result = build_direct_send_quick_replies(
            metadata={
                "buttons": [
                    {"type": "QUICK_REPLY", "text": "Sim, {{1}}"},
                    {"type": "QUICK_REPLY", "text": "Não recebi"},
                    {"type": "QUICK_REPLY", "text": "Ajuda"},
                ]
            },
            template_variables={"1": "Maria"},
            template_name="weni_order_shipped",
        )
        self.assertEqual(result, ["Sim, Maria", "Não recebi", "Ajuda"])
        self.assertTrue(all(isinstance(elem, str) for elem in result))
        self.assertLessEqual(len(result), 3)
