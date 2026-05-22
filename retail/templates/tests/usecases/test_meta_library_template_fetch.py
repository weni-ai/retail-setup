"""Tests for the Direct Send library-catalog fetch helpers (T017).

Covers:

- ``adapt_meta_library_template_response`` — pure adapter shared
  between push-time validation (legacy) and the Direct Send
  assignment branch. Validates components against the supported set
  per ``contracts/meta-library-catalog.md`` §5 and raises
  ``DirectSendUnsupportedComponentError`` on any violation
  (Decision 12).
- ``fetch_meta_library_template_metadata`` — Direct-Send-only HTTP
  wrapper. Calls the service's exact-match fetch and delegates the
  response to the adapter above (research Decision 9).
"""

from unittest.mock import MagicMock

from django.test import TestCase

from retail.agents.domains.agent_integration.exceptions import (
    DirectSendUnsupportedComponentError,
)
from retail.templates.usecases._meta_library_template_fetch import (
    adapt_meta_library_template_response,
    fetch_meta_library_template_metadata,
)


def _typical_response(**overrides):
    base = {
        "name": "weni_order_shipped",
        "language": "pt_BR",
        "category": "UTILITY",
        "body": "Olá {{1}}, seu pedido {{2}} foi enviado.",
        "body_params": ["customer_name", "order_id"],
        "footer": "Equipe Loja XYZ",
        "header": {"type": "TEXT", "text": "Pedido enviado"},
        "buttons": [
            {
                "type": "URL",
                "text": "Acompanhar pedido",
                "url": "https://loja.com/track/{{1}}",
            }
        ],
    }
    base.update(overrides)
    return base


class AdaptMetaLibraryTemplateResponseTest(TestCase):
    def test_returns_template_info_shape_for_typical_response(self):
        result = adapt_meta_library_template_response(_typical_response())

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "weni_order_shipped")
        self.assertEqual(result["content"], "Olá {{1}}, seu pedido {{2}} foi enviado.")

        metadata = result["metadata"]
        self.assertEqual(metadata["body"], "Olá {{1}}, seu pedido {{2}} foi enviado.")
        self.assertEqual(metadata["body_params"], ["customer_name", "order_id"])
        self.assertEqual(metadata["footer"], "Equipe Loja XYZ")
        self.assertEqual(metadata["category"], "UTILITY")
        self.assertEqual(metadata["language"], "pt_BR")
        self.assertEqual(metadata["buttons"][0]["type"], "URL")
        self.assertIsNotNone(metadata["header"])

    def test_returns_none_when_raw_is_none(self):
        self.assertIsNone(adapt_meta_library_template_response(None))

    def test_raises_when_body_is_missing(self):
        raw = _typical_response()
        del raw["body"]
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.template_name, "weni_order_shipped")

    def test_raises_when_body_is_empty(self):
        raw = _typical_response(body="")
        with self.assertRaises(DirectSendUnsupportedComponentError):
            adapt_meta_library_template_response(raw)

    def test_raises_when_unsupported_header_type(self):
        raw = _typical_response(
            header={"type": "VIDEO", "example": "https://example.com/v.mp4"}
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("header", ctx.exception.component_type)

    def test_raises_when_unsupported_button_type(self):
        raw = _typical_response(
            buttons=[
                {"type": "PHONE_NUMBER", "text": "Call", "phone_number": "5511999"}
            ]
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("button", ctx.exception.component_type)

    def test_raises_when_more_than_one_url_button(self):
        raw = _typical_response(
            buttons=[
                {"type": "URL", "text": "A", "url": "https://a.com/{{1}}"},
                {"type": "URL", "text": "B", "url": "https://b.com/{{1}}"},
            ]
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("url_button", ctx.exception.component_type)

    def test_raises_when_more_than_three_quick_reply_buttons(self):
        raw = _typical_response(
            buttons=[
                {"type": "QUICK_REPLY", "text": "Yes"},
                {"type": "QUICK_REPLY", "text": "No"},
                {"type": "QUICK_REPLY", "text": "Maybe"},
                {"type": "QUICK_REPLY", "text": "Other"},
            ]
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("quick_reply_button", ctx.exception.component_type)

    def test_raises_when_body_exceeds_length_limit(self):
        raw = _typical_response(body="x" * 1025)
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("body_length", ctx.exception.component_type)

    def test_raises_when_header_text_exceeds_length_limit(self):
        raw = _typical_response(header={"type": "TEXT", "text": "x" * 61})
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("header_length", ctx.exception.component_type)

    def test_raises_when_footer_exceeds_length_limit(self):
        raw = _typical_response(footer="x" * 61)
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("footer_length", ctx.exception.component_type)

    def test_raises_when_url_button_text_exceeds_length_limit(self):
        raw = _typical_response(
            buttons=[
                {
                    "type": "URL",
                    "text": "x" * 21,
                    "url": "https://loja.com/{{1}}",
                }
            ]
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("button_label_length", ctx.exception.component_type)

    def test_raises_when_quick_reply_text_exceeds_length_limit(self):
        raw = _typical_response(
            buttons=[{"type": "QUICK_REPLY", "text": "x" * 21}]
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("button_label_length", ctx.exception.component_type)

    def test_raises_when_payload_is_malformed(self):
        with self.assertRaises(DirectSendUnsupportedComponentError):
            adapt_meta_library_template_response({"unexpected": "shape"})

    def test_accepts_image_header(self):
        raw = _typical_response(
            header={"type": "IMAGE", "example": "https://cdn.example.com/img.jpg"}
        )
        result = adapt_meta_library_template_response(raw)
        self.assertIsNotNone(result)

    def test_accepts_quick_reply_buttons_within_limit(self):
        raw = _typical_response(
            buttons=[
                {"type": "QUICK_REPLY", "text": "Yes"},
                {"type": "QUICK_REPLY", "text": "No"},
            ]
        )
        result = adapt_meta_library_template_response(raw)
        self.assertIsNotNone(result)

    def test_accepts_response_without_header(self):
        raw = _typical_response()
        del raw["header"]
        result = adapt_meta_library_template_response(raw)
        self.assertIsNotNone(result)
        self.assertIsNone(result["metadata"]["header"])

    def test_raises_when_button_is_not_a_dict(self):
        raw = _typical_response(buttons=["malformed"])
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertIn("button_malformed", ctx.exception.component_type)


class FetchMetaLibraryTemplateMetadataTest(TestCase):
    def test_returns_adapted_metadata_on_service_success(self):
        meta_service = MagicMock()
        meta_service.fetch_library_template_by_name_and_language.return_value = (
            _typical_response()
        )

        result = fetch_meta_library_template_metadata(
            meta_service, "weni_order_shipped", "pt_BR"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "weni_order_shipped")
        meta_service.fetch_library_template_by_name_and_language.assert_called_once_with(
            "weni_order_shipped", "pt_BR"
        )

    def test_returns_none_when_service_returns_none(self):
        meta_service = MagicMock()
        meta_service.fetch_library_template_by_name_and_language.return_value = None

        result = fetch_meta_library_template_metadata(
            meta_service, "weni_order_shipped", "pt_BR"
        )

        self.assertIsNone(result)

    def test_propagates_unsupported_component_error_from_adapter(self):
        meta_service = MagicMock()
        meta_service.fetch_library_template_by_name_and_language.return_value = (
            _typical_response(body="")
        )

        with self.assertRaises(DirectSendUnsupportedComponentError):
            fetch_meta_library_template_metadata(
                meta_service, "weni_order_shipped", "pt_BR"
            )
