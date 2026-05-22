"""Tests for the Direct Send library-catalog fetch helpers (T017 / T107–T111).

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

Phase 8 fold-in (Session 2026-05-22 — T107–T111) extends the adapter's
contract with:

- FR-003e — ``header`` is a plain text string at fetch time; any
  non-string, non-null ``header`` is treated as a malformed response
  and raises ``DirectSendUnsupportedComponentError(component_type="header")``.
- FR-003f — ``buttons[*].type`` outside ``{URL, QUICK_REPLY}`` raises
  ``DirectSendUnsupportedComponentError`` with ``component_type`` set
  to the rejected type string. URL-button entries are normalized from
  EITHER a flat ``url`` string OR the legacy nested
  ``{base_url, url_suffix_example}`` shape to a single canonical flat
  string via ``_ensure_protocol`` + ``_append_placeholder_if_needed``.
- Q3 drop-rule — auxiliary curation fields (``body_param_types``,
  ``attributes``, ``topic``, ``usecase``, ``industry``, ``id``) MUST
  be dropped at fetch time; only the dispatch-relevant subset
  ``{header, body, body_params, footer, buttons, category, language}``
  is propagated to ``TemplateInfo.metadata``.
"""

import logging

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
        "header": "Pedido enviado",
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

    def test_raises_when_unsupported_button_type(self):
        raw = _typical_response(
            buttons=[
                {"type": "PHONE_NUMBER", "text": "Call", "phone_number": "5511999"}
            ]
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "PHONE_NUMBER")

    def test_raises_when_more_than_one_url_button(self):
        raw = _typical_response(
            buttons=[
                {"type": "URL", "text": "A", "url": "https://a.com/{{1}}"},
                {"type": "URL", "text": "B", "url": "https://b.com/{{1}}"},
            ]
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "buttons")

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
        self.assertEqual(ctx.exception.component_type, "buttons")

    def test_raises_when_body_exceeds_length_limit(self):
        raw = _typical_response(body="x" * 1025)
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "body")

    def test_raises_when_header_text_exceeds_length_limit(self):
        raw = _typical_response(header="x" * 61)
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "header")

    def test_raises_when_footer_exceeds_length_limit(self):
        raw = _typical_response(footer="x" * 61)
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "footer")

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
        self.assertEqual(ctx.exception.component_type, "buttons")

    def test_raises_when_quick_reply_text_exceeds_length_limit(self):
        raw = _typical_response(buttons=[{"type": "QUICK_REPLY", "text": "x" * 21}])
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "buttons")

    def test_raises_when_payload_is_malformed(self):
        with self.assertRaises(DirectSendUnsupportedComponentError):
            adapt_meta_library_template_response({"unexpected": "shape"})

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
        self.assertEqual(ctx.exception.component_type, "malformed")


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


class HeaderPlainStringNormalizationTest(TestCase):
    """T107 — FR-003e header plain-string canonical normalization.

    Meta's library catalog ALWAYS returns ``header`` either absent or as
    a plain text string. The adapter MUST normalize it to the canonical
    Retail-internal shape ``{header_type: "TEXT", text: <string>}``
    (``data-model.md §3``) that ``Broadcast.build_direct_send_message``
    and the legacy ``Broadcast.build_broadcast_template_message`` both
    consume via ``header["header_type"]``.
    """

    def test_normalizes_plain_string_header_to_canonical_shape(self):
        raw = _typical_response(header="Pedido enviado")

        result = adapt_meta_library_template_response(raw)

        self.assertIsNotNone(result)
        self.assertEqual(
            result["metadata"]["header"],
            {"header_type": "TEXT", "text": "Pedido enviado"},
        )

    def test_absent_header_produces_none_metadata_header(self):
        raw = _typical_response()
        del raw["header"]

        result = adapt_meta_library_template_response(raw)

        self.assertIsNotNone(result)
        self.assertIsNone(result["metadata"]["header"])


class HeaderDictShapeRejectionTest(TestCase):
    """T108 — FR-003e: dict-shape header is malformed at fetch time.

    Any non-string, non-null ``header`` raises
    ``DirectSendUnsupportedComponentError(component_type="header")``
    so the use case routes through FR-003c (pt_BR retry) and then
    FR-003d (atomic rollback). The pre-FR-003e dict ``{type, text}``
    shape is REJECTED — image / media headers on Direct Send-path
    Templates arise EXCLUSIVELY from post-assignment edits via the
    ``update_template`` endpoint (FR-026), never from the fetch path.
    """

    def test_rejects_dict_header_with_type_text(self):
        raw = _typical_response(header={"type": "TEXT", "text": "Pedido"})

        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)

        self.assertEqual(ctx.exception.component_type, "header")
        self.assertEqual(ctx.exception.template_name, "weni_order_shipped")

    def test_rejects_dict_header_with_type_image(self):
        raw = _typical_response(
            header={"type": "IMAGE", "example": "https://cdn.example.com/img.jpg"}
        )

        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)

        self.assertEqual(ctx.exception.component_type, "header")

    def test_rejects_dict_header_with_arbitrary_shape(self):
        raw = _typical_response(header={"some_key": "some_value"})

        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)

        self.assertEqual(ctx.exception.component_type, "header")

    def test_rejects_non_string_non_dict_header(self):
        raw = _typical_response(header=123)

        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)

        self.assertEqual(ctx.exception.component_type, "header")


class ButtonStrictPerTypeRejectionTest(TestCase):
    """T109 — FR-003f: strict per-type rejection at fetch time.

    Any ``buttons[*].type`` outside ``{URL, QUICK_REPLY}`` — including
    ``PHONE_NUMBER``, ``PAYMENT_REQUEST``, ``ORDER_DETAILS``,
    ``COPY_CODE``, ``FLOW``, or any future Meta-curated value — raises
    ``DirectSendUnsupportedComponentError(component_type=<type>)`` so
    the use case routes through FR-003c → FR-003d. Pinned per-type so
    a future refactor that adds a generic catch-all branch is still
    observable as the spec-intended behaviour rather than a coincidence.
    """

    def _raw_with_button_type(self, btn_type: str, **extra) -> dict:
        return _typical_response(
            buttons=[{"type": btn_type, "text": "Action", **extra}]
        )

    def test_rejects_phone_number_button(self):
        raw = self._raw_with_button_type("PHONE_NUMBER", phone_number="5511999")
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "PHONE_NUMBER")

    def test_rejects_payment_request_button(self):
        raw = self._raw_with_button_type("PAYMENT_REQUEST")
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "PAYMENT_REQUEST")

    def test_rejects_order_details_button(self):
        raw = self._raw_with_button_type("ORDER_DETAILS")
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "ORDER_DETAILS")

    def test_rejects_copy_code_button(self):
        raw = self._raw_with_button_type("COPY_CODE")
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "COPY_CODE")

    def test_rejects_flow_button(self):
        raw = self._raw_with_button_type("FLOW")
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw)
        self.assertEqual(ctx.exception.component_type, "FLOW")

    def test_accepts_url_and_quick_reply_in_same_template(self):
        raw = _typical_response(
            buttons=[
                {
                    "type": "URL",
                    "text": "Track",
                    "url": "https://loja.com/track/{{1}}",
                },
                {"type": "QUICK_REPLY", "text": "Help"},
            ]
        )

        result = adapt_meta_library_template_response(raw)

        self.assertIsNotNone(result)
        self.assertEqual(len(result["metadata"]["buttons"]), 2)


class ButtonUrlShapeNormalizationTest(TestCase):
    """T110 — FR-003f: dual URL-button shape normalization.

    URL-button entries arrive in EITHER (a) flat ``url`` string OR
    (b) legacy nested ``{base_url, url_suffix_example}`` shape; both
    MUST normalize to a flat ``url`` string at persist time via the
    same ``_ensure_protocol`` + ``_append_placeholder_if_needed``
    heuristic the push-path ``ButtonTransformer`` already applies, so
    ``metadata.buttons`` stores a single canonical shape regardless of
    upstream variance.
    """

    def test_flat_url_string_is_preserved_with_placeholder(self):
        raw = _typical_response(
            buttons=[
                {
                    "type": "URL",
                    "text": "Track",
                    "url": "https://loja.com/track/{{1}}",
                }
            ]
        )

        result = adapt_meta_library_template_response(raw)

        self.assertEqual(
            result["metadata"]["buttons"][0]["url"],
            "https://loja.com/track/{{1}}",
        )

    def test_nested_url_with_suffix_example_normalizes_to_flat_string(self):
        raw = _typical_response(
            buttons=[
                {
                    "type": "URL",
                    "text": "Track",
                    "url": {
                        "base_url": "https://loja.com/track/",
                        "url_suffix_example": "{{1}}",
                    },
                }
            ]
        )

        result = adapt_meta_library_template_response(raw)

        self.assertEqual(
            result["metadata"]["buttons"][0]["url"],
            "https://loja.com/track/{{1}}",
        )

    def test_nested_url_missing_protocol_gets_https_prepended(self):
        raw = _typical_response(
            buttons=[
                {
                    "type": "URL",
                    "text": "Track",
                    "url": {
                        "base_url": "loja.com/track/",
                        "url_suffix_example": "{{1}}",
                    },
                }
            ]
        )

        result = adapt_meta_library_template_response(raw)

        self.assertEqual(
            result["metadata"]["buttons"][0]["url"],
            "https://loja.com/track/{{1}}",
        )

    def test_flat_and_nested_shapes_produce_identical_canonical_url(self):
        flat = _typical_response(
            buttons=[
                {
                    "type": "URL",
                    "text": "Track",
                    "url": "https://loja.com/track/{{1}}",
                }
            ]
        )
        nested = _typical_response(
            buttons=[
                {
                    "type": "URL",
                    "text": "Track",
                    "url": {
                        "base_url": "https://loja.com/track/",
                        "url_suffix_example": "{{1}}",
                    },
                }
            ]
        )

        flat_result = adapt_meta_library_template_response(flat)
        nested_result = adapt_meta_library_template_response(nested)

        self.assertEqual(
            flat_result["metadata"]["buttons"][0]["url"],
            nested_result["metadata"]["buttons"][0]["url"],
        )


class AuxiliaryFieldDropTest(TestCase):
    """T111 — Session 2026-05-22 Q3: auxiliary curation fields are dropped.

    Meta's library catalog may carry auxiliary curation fields
    (``body_param_types``, ``attributes``, ``topic``, ``usecase``,
    ``industry``, ``id``). The adapter MUST drop all of them — only the
    dispatch-relevant subset ``{header, body, body_params, footer,
    buttons, category, language}`` propagates to
    ``TemplateInfo.metadata``. The ``direct_send`` audit sub-object is
    added by ``AssignAgentUseCase._create_library_templates`` at write
    time, NOT by the adapter, so this test MUST NOT expect it on the
    adapter return value.
    """

    _FORBIDDEN_AUXILIARY_KEYS = (
        "body_param_types",
        "attributes",
        "topic",
        "usecase",
        "industry",
        "id",
    )

    _ALLOWED_METADATA_KEYS = {
        "header",
        "body",
        "body_params",
        "footer",
        "buttons",
        "category",
        "language",
    }

    def test_auxiliary_fields_are_dropped_from_metadata(self):
        raw = _typical_response(
            body_param_types=["TEXT", "TEXT"],
            attributes={"foo": "bar"},
            topic="order_status",
            usecase="utility_notification",
            industry="ecommerce",
            id="meta-template-id-123",
        )

        result = adapt_meta_library_template_response(raw)

        self.assertIsNotNone(result)
        metadata = result["metadata"]
        for key in self._FORBIDDEN_AUXILIARY_KEYS:
            self.assertNotIn(
                key,
                metadata,
                msg=(
                    f"auxiliary curation field {key!r} must be dropped from "
                    f"metadata at fetch time per Session 2026-05-22 Q3"
                ),
            )

    def test_metadata_keys_are_limited_to_allowed_subset(self):
        raw = _typical_response(
            body_param_types=["TEXT"],
            attributes={"foo": "bar"},
            topic="order_status",
        )

        result = adapt_meta_library_template_response(raw)

        self.assertIsNotNone(result)
        self.assertTrue(
            set(result["metadata"].keys()).issubset(self._ALLOWED_METADATA_KEYS),
            msg=(
                f"metadata keys {set(result['metadata'].keys())!r} must be a "
                f"subset of {self._ALLOWED_METADATA_KEYS!r}; the adapter must "
                f"NOT add the direct_send sub-object — that is the use case's "
                f"responsibility at write time"
            ),
        )

    def test_does_not_add_direct_send_sub_object(self):
        result = adapt_meta_library_template_response(_typical_response())

        self.assertIsNotNone(result)
        self.assertNotIn("direct_send", result["metadata"])


class ButtonLabelOverrideMapTest(TestCase):
    """T112 — FR-003g per-(template_name, language) button-label override map.

    The override map is consulted ONLY when an upstream URL button's
    ``text`` would otherwise overflow ``MAX_BUTTON_LABEL_LENGTH``. The
    map is a remediation for Meta's library catalog occasionally
    publishing button labels longer than the 20-char ceiling on
    locale-translated variants (the canonical real-world example is
    ``order_canceled_3``'s ``"Ver detalhes do pedido"`` in ``pt_BR``
    and ``"Ver detalles del pedido"`` in ``es``).

    Per FR-003g(a) the override applies only at the URL button surface;
    QUICK_REPLY overflows still raise. Per FR-003g(h) an override value
    that itself overflows MUST raise (override is a remediation, not
    a length-check bypass).
    """

    _OVERLONG_PT = "Ver detalhes do pedido"
    _OVERRIDE_PT = "Detalhes do pedido"
    _OVERLONG_ES = "Ver detalles del pedido"
    _OVERRIDE_ES = "Detalles del pedido"

    def test_overflow_with_map_hit_uses_override_pt_br(self):
        raw = _typical_response(
            name="order_canceled_3",
            buttons=[
                {
                    "type": "URL",
                    "text": self._OVERLONG_PT,
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        with self.assertLogs(
            "retail.templates.usecases._meta_library_template_fetch",
            level=logging.INFO,
        ) as captured:
            result = adapt_meta_library_template_response(raw, language="pt_BR")

        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["buttons"][0]["text"], self._OVERRIDE_PT)
        expected_substrings = [
            "direct_send_button_label_overridden",
            "template=order_canceled_3",
            "language=pt_BR",
            f"upstream='{self._OVERLONG_PT}'",
            f"override='{self._OVERRIDE_PT}'",
        ]
        self.assertTrue(
            any(
                all(sub in line for sub in expected_substrings)
                for line in captured.output
            ),
            captured.output,
        )

    def test_overflow_with_map_hit_uses_override_es(self):
        raw = _typical_response(
            name="order_canceled_3",
            buttons=[
                {
                    "type": "URL",
                    "text": self._OVERLONG_ES,
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        result = adapt_meta_library_template_response(raw, language="es")

        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["buttons"][0]["text"], self._OVERRIDE_ES)

    def test_overflow_with_map_miss_raises_buttons(self):
        raw = _typical_response(
            name="unknown_template",
            buttons=[
                {
                    "type": "URL",
                    "text": "An overlong button label",
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw, language="pt_BR")
        self.assertEqual(ctx.exception.component_type, "buttons")

    def test_overflow_with_map_miss_on_wrong_language_raises(self):
        raw = _typical_response(
            name="order_canceled_3",
            buttons=[
                {
                    "type": "URL",
                    "text": self._OVERLONG_PT,
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw, language="fr")
        self.assertEqual(ctx.exception.component_type, "buttons")

    def test_no_overflow_does_not_consult_override(self):
        from retail.agents.domains.agent_webhook.services import (
            direct_send_button_overrides,
        )

        sentinel_map = MagicMock()
        sentinel_map.__contains__ = MagicMock(
            side_effect=AssertionError("override map MUST NOT be consulted")
        )
        sentinel_map.__getitem__ = MagicMock(
            side_effect=AssertionError("override map MUST NOT be consulted")
        )

        raw = _typical_response(
            name="order_canceled_3",
            buttons=[
                {
                    "type": "URL",
                    "text": "View order details",
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        original = direct_send_button_overrides.DIRECT_SEND_BUTTON_LABEL_OVERRIDES
        direct_send_button_overrides.DIRECT_SEND_BUTTON_LABEL_OVERRIDES = sentinel_map
        try:
            result = adapt_meta_library_template_response(raw, language="pt_BR")
        finally:
            direct_send_button_overrides.DIRECT_SEND_BUTTON_LABEL_OVERRIDES = original

        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["buttons"][0]["text"], "View order details")

    def test_overflow_quick_reply_still_raises_regardless_of_map(self):
        raw = _typical_response(
            name="order_canceled_3",
            buttons=[{"type": "QUICK_REPLY", "text": "x" * 21}],
        )
        with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
            adapt_meta_library_template_response(raw, language="pt_BR")
        self.assertEqual(ctx.exception.component_type, "buttons")

    def test_misconfigured_override_value_still_overflows_and_raises(self):
        from unittest.mock import patch as _patch

        from retail.agents.domains.agent_webhook.services import (
            direct_send_button_overrides,
        )

        raw = _typical_response(
            name="test_template",
            buttons=[
                {
                    "type": "URL",
                    "text": "Original overlong text here {{1}}",
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        misconfigured = {("test_template", "pt_BR"): "x" * 21}
        with _patch.object(
            direct_send_button_overrides,
            "DIRECT_SEND_BUTTON_LABEL_OVERRIDES",
            misconfigured,
        ):
            with self.assertRaises(DirectSendUnsupportedComponentError) as ctx:
                adapt_meta_library_template_response(raw, language="pt_BR")
        self.assertEqual(ctx.exception.component_type, "buttons")

    def test_initial_map_contents_are_exactly_two_seed_entries(self):
        from retail.agents.domains.agent_webhook.services.direct_send_button_overrides import (
            DIRECT_SEND_BUTTON_LABEL_OVERRIDES,
        )

        self.assertEqual(len(DIRECT_SEND_BUTTON_LABEL_OVERRIDES), 2)
        self.assertEqual(
            DIRECT_SEND_BUTTON_LABEL_OVERRIDES[("order_canceled_3", "pt_BR")],
            self._OVERRIDE_PT,
        )
        self.assertEqual(
            DIRECT_SEND_BUTTON_LABEL_OVERRIDES[("order_canceled_3", "es")],
            self._OVERRIDE_ES,
        )


class FetchMetaLibraryTemplateMetadataLanguagePropagationTest(TestCase):
    """T112 — language argument MUST be propagated to the adapter so the
    override map can be consulted on overflow per FR-003g.
    """

    def test_language_is_forwarded_to_adapter_for_override_lookup(self):
        meta_service = MagicMock()
        meta_service.fetch_library_template_by_name_and_language.return_value = (
            _typical_response(
                name="order_canceled_3",
                buttons=[
                    {
                        "type": "URL",
                        "text": "Ver detalhes do pedido",
                        "url": "https://loja.com/track/{{1}}",
                    }
                ],
            )
        )

        result = fetch_meta_library_template_metadata(
            meta_service, "order_canceled_3", "pt_BR"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["metadata"]["buttons"][0]["text"], "Detalhes do pedido")
