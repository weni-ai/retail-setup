"""Tests for the Direct Send sample-validation translator.

Pure-function tests covering the four discriminated wire shapes
(non-interactive ``text`` — pure body-only Shape 1 and extended Shape
1b with optional ``header`` and / or ``footer``; ``interactive.cta_url``;
``interactive.button``), variable substitution, deterministic
``reply.id`` derivation, header sub-object dispatch, and the
``parameters`` exclusion rule (Research Decision 9).

The Phase 3c clarification (2026-05-26 round 2 / A13) widened Shape 1
into a super-shape that carries optional ``header`` and / or ``footer``
top-level keys for no-button payloads. The
``BuildMetaSampleBodyExtendedShape1bTest`` class below pins the four
no-button-with-extras combinations end-to-end at the translator
boundary.
"""

from unittest import TestCase

from retail.templates.adapters.direct_send_sample_translator import (
    build_meta_sample_body,
)
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleDTO,
)


def _dto(**overrides) -> ValidateTemplateSampleDTO:
    """Build a DTO with sane defaults for the test cases."""
    defaults = dict(
        template_uuid="0fa1c8e2-9b6f-4f3e-9aa2-2c4ddc0e7e11",
        template_body=None,
        template_header=None,
        template_footer=None,
        template_button=None,
        template_body_params=None,
        app_uuid="a1b2c3d4-1111-2222-3333-444455556666",
        project_uuid="11111111-2222-3333-4444-555566667777",
        parameters=None,
        language="pt_BR",
    )
    defaults.update(overrides)
    return ValidateTemplateSampleDTO(**defaults)


class BuildMetaSampleBodyTextShapeTest(TestCase):
    def test_body_only_payload_produces_text_shape(self):
        dto = _dto(template_body="Olá João")

        body = build_meta_sample_body(dto)

        self.assertEqual(body, {"type": "text", "text": {"body": "Olá João"}})

    def test_body_only_payload_substitutes_placeholders(self):
        dto = _dto(
            template_body="Olá {{1}}, pedido #{{2}}",
            template_body_params=["João", "1234"],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(body["text"]["body"], "Olá João, pedido #1234")


class BuildMetaSampleBodyCtaUrlShapeTest(TestCase):
    def test_cta_url_with_text_header_produces_full_shape(self):
        dto = _dto(
            template_body="Olá",
            template_header="Pedido entregue",
            template_footer="Equipe XYZ",
            template_button=[
                {
                    "type": "URL",
                    "text": "Confirmar",
                    "url": {
                        "base_url": "https://loja.example.com/confirmar",
                        "url_suffix_example": "abc123",
                    },
                }
            ],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(body["type"], "interactive")
        interactive = body["interactive"]
        self.assertEqual(interactive["type"], "cta_url")
        self.assertEqual(interactive["header"]["type"], "text")
        self.assertEqual(interactive["header"]["text"], "Pedido entregue")
        self.assertEqual(interactive["body"], {"text": "Olá"})
        self.assertEqual(interactive["footer"], {"text": "Equipe XYZ"})
        self.assertEqual(interactive["action"]["name"], "cta_url")
        self.assertEqual(
            interactive["action"]["parameters"]["display_text"], "Confirmar"
        )

    def test_cta_url_with_image_header_uses_resolved_url(self):
        dto = _dto(
            template_body="Body",
            template_header="data:image/png;base64,abc==",
            template_button=[
                {
                    "type": "URL",
                    "text": "Click",
                    "url": "https://x/{{1}}",
                }
            ],
        )

        body = build_meta_sample_body(
            dto, resolved_header_url="https://s3.example.com/header.png"
        )

        header = body["interactive"]["header"]
        self.assertEqual(
            header,
            {
                "type": "image",
                "image": {"link": "https://s3.example.com/header.png"},
            },
        )

    def test_cta_url_with_base_url_and_suffix_appends_placeholder_and_substitutes(self):
        dto = _dto(
            template_body="Body",
            template_button=[
                {
                    "type": "URL",
                    "text": "Open",
                    "url": {
                        "base_url": "https://loja.example.com/confirmar/",
                        "url_suffix_example": "abc123",
                    },
                }
            ],
            template_body_params=["xyz789"],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body["interactive"]["action"]["parameters"]["url"],
            "https://loja.example.com/confirmar/xyz789",
        )

    def test_cta_url_with_flat_string_url_preserves_verbatim(self):
        dto = _dto(
            template_body="Body",
            template_button=[
                {
                    "type": "URL",
                    "text": "Open",
                    "url": "https://loja.example.com/{{1}}",
                }
            ],
            template_body_params=["abc123"],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body["interactive"]["action"]["parameters"]["url"],
            "https://loja.example.com/abc123",
        )

    def test_cta_url_skips_header_when_absent(self):
        dto = _dto(
            template_body="Body",
            template_button=[
                {
                    "type": "URL",
                    "text": "Click",
                    "url": {"base_url": "https://example.com"},
                }
            ],
        )

        body = build_meta_sample_body(dto)

        self.assertNotIn("header", body["interactive"])
        self.assertEqual(
            body["interactive"]["action"]["parameters"]["url"],
            "https://example.com",
        )


class BuildMetaSampleBodyReplyButtonsShapeTest(TestCase):
    def test_single_reply_button(self):
        dto = _dto(
            template_body="Body",
            template_button=[
                {"type": "QUICK_REPLY", "text": "Ver detalhes"},
            ],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(body["interactive"]["type"], "button")
        buttons = body["interactive"]["action"]["buttons"]
        self.assertEqual(len(buttons), 1)
        self.assertEqual(
            buttons[0],
            {"type": "reply", "reply": {"id": "ver_detalhes", "title": "Ver detalhes"}},
        )

    def test_three_reply_buttons(self):
        dto = _dto(
            template_body="Body",
            template_button=[
                {"type": "QUICK_REPLY", "text": "Sim"},
                {"type": "QUICK_REPLY", "text": "Não"},
                {"type": "QUICK_REPLY", "text": "Cancelar pedido"},
            ],
        )

        body = build_meta_sample_body(dto)

        buttons = body["interactive"]["action"]["buttons"]
        self.assertEqual(len(buttons), 3)
        self.assertEqual(buttons[0]["reply"]["id"], "sim")
        self.assertEqual(buttons[2]["reply"]["id"], "cancelar_pedido")

    def test_duplicate_text_buttons_get_disambiguated_ids(self):
        dto = _dto(
            template_body="Body",
            template_button=[
                {"type": "QUICK_REPLY", "text": "Ok"},
                {"type": "QUICK_REPLY", "text": "Ok"},
                {"type": "QUICK_REPLY", "text": "Ok"},
            ],
        )

        body = build_meta_sample_body(dto)

        buttons = body["interactive"]["action"]["buttons"]
        ids = [b["reply"]["id"] for b in buttons]
        self.assertEqual(ids, ["ok", "ok_2", "ok_3"])
        for button in buttons:
            self.assertLessEqual(len(button["reply"]["id"]), 64)


class BuildMetaSampleBodyVariableSubstitutionTest(TestCase):
    def test_substitution_fires_across_all_text_fields(self):
        dto = _dto(
            template_body="Body {{1}}",
            template_header="Header {{1}}",
            template_footer="Footer {{1}}",
            template_button=[
                {
                    "type": "URL",
                    "text": "Button {{1}}",
                    "url": "https://example.com/{{1}}",
                }
            ],
            template_body_params=["VALUE"],
        )

        body = build_meta_sample_body(dto)

        interactive = body["interactive"]
        self.assertEqual(interactive["header"]["text"], "Header VALUE")
        self.assertEqual(interactive["body"]["text"], "Body VALUE")
        self.assertEqual(interactive["footer"]["text"], "Footer VALUE")
        self.assertEqual(
            interactive["action"]["parameters"]["display_text"], "Button VALUE"
        )
        self.assertEqual(
            interactive["action"]["parameters"]["url"], "https://example.com/VALUE"
        )

    def test_missing_index_substitutes_to_empty_string_and_warns(self):
        dto = _dto(
            template_body="Hi {{1}} and {{2}}",
            template_body_params=["only-one"],
        )

        with self.assertLogs(
            "retail.agents.domains.agent_webhook.services.direct_send_payload_builder",
            level="WARNING",
        ):
            body = build_meta_sample_body(dto)

        self.assertEqual(body["text"]["body"], "Hi only-one and ")

    def test_parameters_field_is_not_consulted_as_substitution_source(self):
        dto = _dto(
            template_body="Hello {{1}}",
            parameters=[{"name": "role", "value": "manager"}],
        )

        body = build_meta_sample_body(dto)

        rendered = body["text"]["body"]
        self.assertNotIn("manager", rendered)
        self.assertEqual(rendered, "Hello ")


class BuildMetaSampleBodyHeaderDispatchTest(TestCase):
    def test_text_header_without_image_marker_routes_to_text_subobject(self):
        dto = _dto(
            template_body="Body",
            template_header="Plain text",
            template_button=[
                {
                    "type": "URL",
                    "text": "Click",
                    "url": "https://example.com",
                }
            ],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body["interactive"]["header"],
            {"type": "text", "text": "Plain text"},
        )

    def test_http_url_header_routes_to_image_subobject_without_resolved_url(self):
        dto = _dto(
            template_body="Body",
            template_header="https://existing-bucket.s3.amazonaws.com/image.png",
            template_button=[
                {
                    "type": "URL",
                    "text": "Click",
                    "url": "https://example.com",
                }
            ],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body["interactive"]["header"],
            {
                "type": "image",
                "image": {"link": "https://existing-bucket.s3.amazonaws.com/image.png"},
            },
        )


class BuildMetaSampleBodyExtendedShape1bTest(TestCase):
    """Extended Shape 1b — no-button payloads with optional header / footer.

    Pins FR-004 (post-clarification 2026-05-26 round 2) / FR-004a / A13:
    no-button payloads emit a four-key super-shape ``{"type": "text",
    "header": {...}?, "footer": {...}?, "text": {"body": ...}}``. The
    optional keys are ABSENT (not ``null``) when the input field is
    missing — degenerate Shape 1b reduces bit-identically to Shape 1.

    The bug case (test (a) below) reproduces the literal payload
    reported 2026-05-26: ``{template_body, template_header: "Pedido
    recebido", template_button: []}`` was producing ``{"type": "text",
    "text": {"body": ...}}`` with the header silently dropped.
    """

    def test_text_header_no_footer_no_buttons_emits_extended_shape_1b(self):
        dto = _dto(
            template_body="Olá {{1}}!\n\nRecebemos seu pedido {{2}}.",
            template_header="Pedido recebido",
            template_body_params=["John", "nº 12345"],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body,
            {
                "type": "text",
                "header": {"type": "text", "text": "Pedido recebido"},
                "text": {"body": "Olá John!\n\nRecebemos seu pedido nº 12345."},
            },
        )

    def test_image_http_url_header_no_footer_no_buttons_emits_extended_shape_1b(self):
        dto = _dto(
            template_body="Body",
            template_header="https://example.com/banner.png",
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body,
            {
                "type": "text",
                "header": {
                    "type": "image",
                    "image": {"link": "https://example.com/banner.png"},
                },
                "text": {"body": "Body"},
            },
        )

    def test_image_base64_header_no_footer_no_buttons_uses_resolved_s3_url(self):
        dto = _dto(
            template_body="Body",
            template_header="data:image/png;base64,abc==",
        )

        body = build_meta_sample_body(
            dto,
            resolved_header_url="https://retail-bucket.s3.amazonaws.com/template_headers/abc.png",
        )

        self.assertEqual(
            body["header"],
            {
                "type": "image",
                "image": {
                    "link": "https://retail-bucket.s3.amazonaws.com/template_headers/abc.png"
                },
            },
        )
        self.assertNotIn("abc==", body["header"]["image"]["link"])

    def test_footer_only_no_header_no_buttons_emits_extended_shape_1b(self):
        dto = _dto(
            template_body="Body",
            template_footer="Equipe XYZ",
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body,
            {
                "type": "text",
                "footer": {"text": "Equipe XYZ"},
                "text": {"body": "Body"},
            },
        )
        self.assertNotIn("header", body)

    def test_text_header_with_footer_no_buttons_emits_extended_shape_1b(self):
        dto = _dto(
            template_body="Body",
            template_header="Header",
            template_footer="Footer",
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(
            body,
            {
                "type": "text",
                "header": {"type": "text", "text": "Header"},
                "footer": {"text": "Footer"},
                "text": {"body": "Body"},
            },
        )

    def test_pure_body_only_payload_reduces_to_shape_1_bit_identically(self):
        """REGRESSION — degenerate Shape 1b reduces to the pre-existing Shape 1.

        No ``header`` / ``footer`` keys are emitted when the
        corresponding inputs are missing — ensures pre-Phase-3c
        body-only callers see no observable wire-shape drift.
        """
        dto = _dto(template_body="Olá João")

        body = build_meta_sample_body(dto)

        self.assertEqual(body, {"type": "text", "text": {"body": "Olá João"}})
        self.assertNotIn("header", body)
        self.assertNotIn("footer", body)

    def test_substitution_fires_across_text_header_body_footer_in_extended_shape_1b(self):
        dto = _dto(
            template_body="Body {{1}}",
            template_header="Header {{1}}",
            template_footer="Footer {{1}}",
            template_body_params=["VALUE"],
        )

        body = build_meta_sample_body(dto)

        self.assertEqual(body["header"]["text"], "Header VALUE")
        self.assertEqual(body["text"]["body"], "Body VALUE")
        self.assertEqual(body["footer"]["text"], "Footer VALUE")

    def test_missing_index_substitutes_to_empty_string_in_extended_shape_1b(self):
        dto = _dto(
            template_body="Hello {{1}} and {{2}}",
            template_header="Hi {{1}}",
            template_footer="Bye {{2}}",
            template_body_params=["only-one"],
        )

        with self.assertLogs(
            "retail.agents.domains.agent_webhook.services.direct_send_payload_builder",
            level="WARNING",
        ):
            body = build_meta_sample_body(dto)

        self.assertEqual(body["header"]["text"], "Hi only-one")
        self.assertEqual(body["text"]["body"], "Hello only-one and ")
        self.assertEqual(body["footer"]["text"], "Bye ")
