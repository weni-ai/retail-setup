"""Regression guards for ``Broadcast.build_direct_send_message``.

Anchor: FR-014a / FR-014b / FR-014c / FR-014d / FR-017 / FR-039 /
FR-044 (enforced at ``retail.agents.domains.agent_webhook.services.broadcast``).
"""

import logging

from typing import Any, Dict, List

from uuid import uuid4

from django.test import TestCase

from unittest.mock import MagicMock

from retail.agents.domains.agent_webhook.services.broadcast import Broadcast


_BUILDER_LOGGER = "retail.agents.domains.agent_webhook.services.broadcast"


def _make_template(
    *,
    name: str = "weni_order_shipped",
    body: str = "Olá {{1}}, seu pedido {{2}} foi enviado.",
    header: Dict[str, Any] = None,
    footer: str = None,
    buttons: List[Dict[str, Any]] = None,
    language: str = "pt_BR",
):
    template = MagicMock()
    template.current_version.template_name = name
    template.name = name
    metadata: Dict[str, Any] = {"body": body, "language": language}
    if header is not None:
        metadata["header"] = header
    if footer is not None:
        metadata["footer"] = footer
    if buttons is not None:
        metadata["buttons"] = buttons
    template.metadata = metadata
    return template


def _make_integrated_agent(*, project_uuid=None, agent_uuid=None, direct_send=True):
    integrated_agent = MagicMock()
    integrated_agent.uuid = uuid4()
    integrated_agent.channel_uuid = uuid4()
    integrated_agent.project.uuid = project_uuid or uuid4()
    integrated_agent.agent.uuid = agent_uuid or uuid4()
    integrated_agent.config = {"direct_send": direct_send} if direct_send else {}
    return integrated_agent


class BuildDirectSendMessageHappyPathTest(TestCase):
    """Happy-path Direct Send wire shape. Anchor: FR-014a / FR-014c / FR-014d."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def test_as1_body_with_two_variables_substituted_and_direct_send_flag(self):
        """Canonical Direct Send wire shape. Anchor: FR-014c / FR-014d."""
        template = _make_template(
            body="Olá {{1}}, seu pedido {{2}} foi enviado.",
        )
        data = {
            "template_variables": {"1": "Maria", "2": "12345"},
            "contact_urn": "whatsapp:5598123456789",
        }
        result = self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["project"], str(self.integrated_agent.project.uuid))
        self.assertEqual(result["urns"], ["whatsapp:5598123456789"])
        self.assertEqual(result["channel"], str(self.integrated_agent.channel_uuid))
        self.assertIs(result["msg"]["direct_send"], True)
        self.assertEqual(result["msg"]["category"], "utility")
        self.assertEqual(
            result["msg"]["direct_send_template_name"], "weni_order_shipped"
        )
        self.assertEqual(
            result["msg"]["text"], "Olá Maria, seu pedido 12345 foi enviado."
        )
        self.assertNotIn("template", result["msg"])
        self.assertNotIn("body", result["msg"])
        self.assertNotIn("locale", result["msg"])
        self.assertNotIn("language", result["msg"])
        self.assertNotIn("buttons", result["msg"])
        self.assertNotIn("header", result["msg"])
        self.assertNotIn("attachments", result["msg"])

    def test_as2_image_header_and_cta_url_button(self):
        """CTA URL is emitted via ``msg.cta_message``. Anchor: FR-014a."""
        template = _make_template(
            body="Olá {{1}}, seu pedido {{2}} chegou.",
            header={"header_type": "IMAGE", "text": "image-placeholder"},
            buttons=[
                {
                    "type": "URL",
                    "text": "Acompanhar pedido",
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        data = {
            "template_variables": {
                "1": "Maria",
                "2": "12345",
                "image_url": "https://cdn.loja.com/order_12345.jpg",
            },
            "contact_urn": "whatsapp:5598123456789",
        }
        result = self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            result["msg"]["header"],
            {
                "type": "image",
                "image_url": "https://cdn.loja.com/order_12345.jpg",
            },
        )
        self.assertEqual(
            result["msg"]["attachments"],
            ["image/jpeg:https://cdn.loja.com/order_12345.jpg"],
        )
        self.assertEqual(result["msg"]["interaction_type"], "cta_url")
        self.assertEqual(
            result["msg"]["cta_message"],
            {
                "display_text": "Acompanhar pedido",
                "url": "https://loja.com/track/Maria",
            },
        )
        self.assertNotIn("buttons", result["msg"])
        self.assertEqual(result["msg"]["text"], "Olá Maria, seu pedido 12345 chegou.")
        self.assertNotIn("body", result["msg"])
        self.assertNotIn("template", result["msg"])

    def test_as3_body_only_no_variables_no_buttons_no_header(self):
        template = _make_template(
            body="Olá cliente, sua nota fiscal foi emitida.",
        )
        data = {
            "template_variables": {},
            "contact_urn": "whatsapp:5598123456789",
        }
        result = self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )
        self.assertIsNotNone(result)
        self.assertEqual(
            result["msg"]["text"], "Olá cliente, sua nota fiscal foi emitida."
        )
        self.assertNotIn("body", result["msg"])
        self.assertNotIn("template", result["msg"])
        self.assertNotIn("buttons", result["msg"])
        self.assertNotIn("header", result["msg"])
        self.assertNotIn("attachments", result["msg"])
        self.assertNotIn("footer", result["msg"])

    def test_footer_is_substituted_when_present(self):
        template = _make_template(
            body="Olá {{1}}.",
            footer="Equipe Loja XYZ {{1}}",
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:5598123456789",
        }
        result = self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )
        self.assertEqual(result["msg"]["footer"], "Equipe Loja XYZ Maria")

    def test_text_header_is_substituted_when_present(self):
        template = _make_template(
            body="Olá {{1}}.",
            header={"header_type": "TEXT", "text": "Pedido {{2}}"},
        )
        data = {
            "template_variables": {"1": "Maria", "2": "12345"},
            "contact_urn": "whatsapp:5598123456789",
        }
        result = self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )
        self.assertEqual(
            result["msg"]["header"], {"type": "text", "text": "Pedido 12345"}
        )
        self.assertNotIn("attachments", result["msg"])


class BuildDirectSendMessageQuickReplyWireShapeTest(TestCase):
    """QUICK_REPLY wire shape on Direct Send. Anchor: FR-014b."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def _build(self, template, data):
        return self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )

    def test_three_quick_replies_emit_flat_array_no_buttons_key(self):
        template = _make_template(
            body="Olá {{1}}, confirme seu pedido.",
            buttons=[
                {"type": "QUICK_REPLY", "text": "Sim, {{1}}"},
                {"type": "QUICK_REPLY", "text": "Não recebi"},
                {"type": "QUICK_REPLY", "text": "Ajuda"},
            ],
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:5598123456789",
        }
        result = self._build(template, data)
        self.assertIsNotNone(result)
        self.assertEqual(
            result["msg"]["quick_replies"], ["Sim, Maria", "Não recebi", "Ajuda"]
        )
        self.assertNotIn("buttons", result["msg"])

    def test_order_is_preserved(self):
        template = _make_template(
            body="Body",
            buttons=[
                {"type": "QUICK_REPLY", "text": "Sim"},
                {"type": "QUICK_REPLY", "text": "Não"},
                {"type": "QUICK_REPLY", "text": "Cancelar"},
            ],
        )
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertEqual(result["msg"]["quick_replies"], ["Sim", "Não", "Cancelar"])

    def test_id_field_is_not_carried_on_the_wire(self):
        """Meta's catalog ``id`` is dropped at the wire. Anchor: FR-014b."""
        template = _make_template(
            body="Body",
            buttons=[{"type": "QUICK_REPLY", "id": "yes_track", "text": "Acompanhar"}],
        )
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertTrue(
            all(isinstance(elem, str) for elem in result["msg"]["quick_replies"])
        )
        self.assertEqual(result["msg"]["quick_replies"], ["Acompanhar"])

    def test_variable_substitution_applies_to_quick_reply_titles(self):
        template = _make_template(
            body="Body",
            buttons=[{"type": "QUICK_REPLY", "text": "Acompanhar {{1}}"}],
        )
        data = {
            "template_variables": {"1": "12345"},
            "contact_urn": "whatsapp:55",
        }
        result = self._build(template, data)
        self.assertEqual(result["msg"]["quick_replies"], ["Acompanhar 12345"])

    def test_quick_reply_title_over_20_chars_refuses(self):
        template = _make_template(
            body="Body",
            buttons=[{"type": "QUICK_REPLY", "text": "x" * 20 + " {{1}}"}],
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self._build(template, data)
        self.assertIsNone(result)
        self.assertTrue(
            any(
                "skipped_due_to_direct_send_validation" in line
                and "reason=component_length_limit" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_combined_url_and_quick_replies_emit_parallel_siblings(self):
        """URL + QUICK_REPLY surfaces are independent. Anchor: FR-014b(f)."""
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Acompanhar",
                    "url": "https://loja.com/track",
                },
                {"type": "QUICK_REPLY", "text": "Sim"},
                {"type": "QUICK_REPLY", "text": "Não"},
            ],
        )
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertIsNotNone(result)
        self.assertEqual(result["msg"]["interaction_type"], "cta_url")
        self.assertEqual(
            result["msg"]["cta_message"],
            {"display_text": "Acompanhar", "url": "https://loja.com/track"},
        )
        self.assertEqual(result["msg"]["quick_replies"], ["Sim", "Não"])
        self.assertNotIn("buttons", result["msg"])

    def test_interaction_type_is_absent_when_only_quick_replies_present(self):
        template = _make_template(
            body="Olá.",
            buttons=[
                {"type": "QUICK_REPLY", "text": "Sim"},
                {"type": "QUICK_REPLY", "text": "Não"},
            ],
        )
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertNotIn("interaction_type", result["msg"])
        self.assertNotIn("cta_message", result["msg"])
        self.assertEqual(result["msg"]["quick_replies"], ["Sim", "Não"])
        self.assertNotIn("buttons", result["msg"])


class BuildDirectSendMessageNamingRuleRefusalTest(TestCase):
    """Naming-rule refusal path. Anchor: FR-017 / Research Decision 7."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def _assert_refusal(self, name: str):
        template = _make_template(name=name, body="Olá.")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self.handler.build_direct_send_message(
                data=data,
                channel_uuid=str(self.integrated_agent.channel_uuid),
                project_uuid=str(self.integrated_agent.project.uuid),
                template=template,
                integrated_agent=self.integrated_agent,
            )
        self.assertIsNone(result)
        expected_substrings = [
            "[BroadcastDispatch] skipped_due_to_direct_send_validation",
            f"project_uuid={self.integrated_agent.project.uuid}",
            f"template={name}",
            "reason=naming_rule",
        ]
        self.assertTrue(
            any(
                all(sub in line for sub in expected_substrings)
                for line in captured.output
            ),
            captured.output,
        )

    def test_uppercase_name_refuses_with_naming_rule_log(self):
        self._assert_refusal("Weni_Order_Shipped")

    def test_hyphenated_name_refuses_with_naming_rule_log(self):
        self._assert_refusal("weni-order-shipped")

    def test_non_ascii_name_refuses_with_naming_rule_log(self):
        self._assert_refusal("weni_order_envío")

    def test_overlong_name_refuses_with_naming_rule_log(self):
        self._assert_refusal("a" * 513)


class BuildDirectSendMessageMissingContactUrnTest(TestCase):
    """Defensive guard against missing ``contact_urn``."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def test_missing_contact_urn_logs_error_and_returns_none(self):
        template = _make_template(body="Olá {{1}}.")
        data = {"template_variables": {"1": "Maria"}}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.ERROR) as captured:
            result = self.handler.build_direct_send_message(
                data=data,
                channel_uuid=str(self.integrated_agent.channel_uuid),
                project_uuid=str(self.integrated_agent.project.uuid),
                template=template,
                integrated_agent=self.integrated_agent,
            )
        self.assertIsNone(result)
        self.assertTrue(
            any(
                "Incomplete Direct Send message data" in line
                and "weni_order_shipped" in line
                for line in captured.output
            ),
            captured.output,
        )


class BuildDirectSendMessageLengthAndEmptyBodyRefusalTest(TestCase):
    """Contract §4 rule-2 / rule-3 refusal paths (T011c)."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def _build(self, template, data):
        return self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )

    def _assert_refusal_reason(self, captured_output, reason):
        expected_substrings = [
            "[BroadcastDispatch] skipped_due_to_direct_send_validation",
            f"project_uuid={self.integrated_agent.project.uuid}",
            f"reason={reason}",
        ]
        self.assertTrue(
            any(
                all(sub in line for sub in expected_substrings)
                for line in captured_output
            ),
            captured_output,
        )

    def test_empty_body_refuses_with_empty_body_reason(self):
        template = _make_template(body="")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self.assertIsNone(self._build(template, data))
        self._assert_refusal_reason(captured.output, "empty_body")

    def test_missing_body_refuses_with_empty_body_reason(self):
        template = MagicMock()
        template.current_version.template_name = "weni_order_shipped"
        template.metadata = {"language": "pt_BR"}
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self.assertIsNone(self._build(template, data))
        self._assert_refusal_reason(captured.output, "empty_body")

    def test_body_over_1024_chars_after_substitution_refuses(self):
        template = _make_template(body="x" * 1024 + " {{1}}")
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self.assertIsNone(self._build(template, data))
        self._assert_refusal_reason(captured.output, "component_length_limit")

    def test_header_text_over_60_chars_after_substitution_refuses(self):
        template = _make_template(
            body="Olá.",
            header={"header_type": "TEXT", "text": "x" * 60 + " {{1}}"},
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self.assertIsNone(self._build(template, data))
        self._assert_refusal_reason(captured.output, "component_length_limit")

    def test_footer_over_60_chars_after_substitution_refuses(self):
        template = _make_template(
            body="Olá.",
            footer="x" * 60 + " {{1}}",
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self.assertIsNone(self._build(template, data))
        self._assert_refusal_reason(captured.output, "component_length_limit")

    def test_cta_button_display_text_over_20_chars_refuses(self):
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Texto muito longo aqui {{1}}",
                    "url": "https://loja.com/track",
                }
            ],
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self.assertIsNone(self._build(template, data))
        self._assert_refusal_reason(captured.output, "component_length_limit")

    def test_quick_reply_title_over_20_chars_refuses(self):
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "QUICK_REPLY",
                    "text": "x" * 20 + " {{1}}",
                }
            ],
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self.assertIsNone(self._build(template, data))
        self._assert_refusal_reason(captured.output, "component_length_limit")

    def test_cta_button_url_over_20_chars_is_allowed(self):
        """``url`` bypasses the 20-char gate per contract §3.3."""
        long_url = "https://loja.com/track/" + "x" * 100
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Acompanhar",
                    "url": long_url + "{{1}}",
                }
            ],
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        result = self._build(template, data)
        self.assertIsNotNone(result)
        self.assertNotIn("buttons", result["msg"])
        self.assertEqual(result["msg"]["cta_message"]["url"], long_url + "Maria")


class BuildDirectSendMessageCtaUrlWireShapeTest(TestCase):
    """CTA URL wire shape on Direct Send. Anchor: FR-013 / FR-014a."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def _build(self, template, data):
        return self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )

    def test_url_only_emits_cta_message_siblings_no_buttons_key(self):
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Acompanhar pedido",
                    "url": "https://loja.com/track/{{1}}",
                }
            ],
        )
        data = {
            "template_variables": {"1": "12345"},
            "contact_urn": "whatsapp:55",
        }
        result = self._build(template, data)
        self.assertIsNotNone(result)
        self.assertEqual(result["msg"]["interaction_type"], "cta_url")
        self.assertEqual(
            result["msg"]["cta_message"],
            {
                "display_text": "Acompanhar pedido",
                "url": "https://loja.com/track/12345",
            },
        )
        self.assertNotIn("buttons", result["msg"])

    def test_discriminator_key_spelled_interaction_type_not_interactive(self):
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Acompanhar",
                    "url": "https://loja.com/track",
                }
            ],
        )
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertIn("interaction_type", result["msg"])
        self.assertNotIn("interactive_type", result["msg"])

    def test_variable_substitution_on_both_display_text_and_url(self):
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Acomp {{1}}",
                    "url": "https://loja.com/track/{{2}}",
                }
            ],
        )
        data = {
            "template_variables": {"1": "Maria", "2": "12345"},
            "contact_urn": "whatsapp:55",
        }
        result = self._build(template, data)
        self.assertEqual(result["msg"]["cta_message"]["display_text"], "Acomp Maria")
        self.assertEqual(
            result["msg"]["cta_message"]["url"], "https://loja.com/track/12345"
        )

    def test_cta_message_display_text_over_20_chars_refuses(self):
        template = _make_template(
            body="Olá.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Texto muito longo aqui {{1}}",
                    "url": "https://loja.com/track",
                }
            ],
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self._build(template, data)
        self.assertIsNone(result)
        self.assertTrue(
            any(
                "skipped_due_to_direct_send_validation" in line
                and f"project_uuid={self.integrated_agent.project.uuid}" in line
                and "reason=component_length_limit" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_url_over_200_chars_is_allowed(self):
        long_url = "https://loja.com/track/" + "x" * 200
        template = _make_template(
            body="Olá.",
            buttons=[{"type": "URL", "text": "Acomp", "url": long_url + "{{1}}"}],
        )
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        result = self._build(template, data)
        self.assertIsNotNone(result)
        self.assertEqual(result["msg"]["cta_message"]["url"], long_url + "Maria")
        self.assertNotIn("buttons", result["msg"])


class BuildMessageNoLocalTemplateEdgeCaseTest(TestCase):
    """Direct Send-enabled agent with no local template. Anchor: FR-027 / FR-039."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent(direct_send=True)
        self.integrated_agent.templates.filter.return_value.select_related.return_value.first.return_value = (
            None
        )

    def test_returns_none_without_invoking_direct_send_builder(self):
        data = {
            "template": "nonexistent_template",
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self.handler.build_message(self.integrated_agent, data)
        self.assertIsNone(result)
        legacy_shape_hits = [
            line for line in captured.output if "not found" in line.lower()
        ]
        self.assertTrue(legacy_shape_hits, captured.output)
        direct_send_validation_hits = [
            line
            for line in captured.output
            if "skipped_due_to_direct_send_validation" in line
        ]
        self.assertEqual(direct_send_validation_hits, [])


class BuildDirectSendMessageTemplateNameWireShapeTest(TestCase):
    """Template-name wire shape on Direct Send. Anchor: FR-014c."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def _build(self, template, data):
        return self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )

    def test_msg_template_is_dropped(self):
        template = _make_template(body="Olá.")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertIsNotNone(result)
        self.assertNotIn("template", result["msg"])

    def test_direct_send_template_name_carries_local_template_name(self):
        template = _make_template(name="weni_order_invoiced", body="Olá.")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertEqual(
            result["msg"]["direct_send_template_name"], "weni_order_invoiced"
        )

    def test_direct_send_template_name_is_a_top_level_string(self):
        template = _make_template(body="Olá.")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        self.assertIsInstance(result["msg"].get("direct_send_template_name"), str)
        with self.assertRaises(TypeError):
            result["msg"]["direct_send_template_name"]["name"]  # noqa: B018

    def test_locale_is_dropped_from_the_wire(self):
        """No language hint on the wire. Anchor: FR-014c(f)."""
        template = _make_template(
            name="weni_order_shipped", body="Olá.", language="es_MX"
        )
        data = {
            "template_variables": {},
            "contact_urn": "whatsapp:55",
            "language": "es_MX",
        }
        result = self._build(template, data)
        self.assertIsNotNone(result)
        self.assertNotIn("locale", result["msg"])
        self.assertNotIn("language", result["msg"])
        self.assertNotIn("template", result["msg"])
        self.assertTrue(callable(getattr(self.handler, "_resolve_language", None)))

    def test_naming_rule_refusal_still_gates_the_wire_identifier(self):
        """Naming-rule gate runs before wire emission. Anchor: FR-014c(b) / FR-017."""
        template = _make_template(name="Weni-Order-Invoiced", body="Olá.")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self._build(template, data)
        self.assertIsNone(result)
        self.assertTrue(
            any(
                "skipped_due_to_direct_send_validation" in line
                and "reason=naming_rule" in line
                and "template=Weni-Order-Invoiced" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_audit_log_keeps_template_field_unchanged(self):
        """Audit-log ``template=`` field is not renamed. Anchor: FR-014c(d)."""
        template = _make_template(name="weni_order_empty", body="")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            self._build(template, data)
        self.assertTrue(
            any(
                "skipped_due_to_direct_send_validation" in line
                and "template=weni_order_empty" in line
                and "reason=empty_body" in line
                for line in captured.output
            ),
            captured.output,
        )
        for line in captured.output:
            self.assertNotIn("direct_send_template_name=", line)


class BuildDirectSendMessageBodyTextRenameWireShapeTest(TestCase):
    """Wire-only ``msg.body`` -> ``msg.text`` rename. Anchor: FR-014d."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def _build(self, template, data):
        return self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )

    def test_wire_key_is_exactly_text(self):
        template = _make_template(body="Olá {{1}}")
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        result = self._build(template, data)
        self.assertEqual(result["msg"]["text"], "Olá Maria")
        self.assertNotIn("body", result["msg"])

    def test_text_is_top_level_sibling_string(self):
        template = _make_template(body="Olá.")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        result = self._build(template, data)
        msg = result["msg"]
        self.assertIsInstance(msg["text"], str)
        self.assertIn("direct_send", msg)
        self.assertIn("category", msg)
        self.assertIn("direct_send_template_name", msg)

    def test_empty_body_refusal_preserves_empty_body_reason(self):
        template = _make_template(body="")
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self._build(template, data)
        self.assertIsNone(result)
        self.assertTrue(
            any(
                "reason=empty_body" in line and "reason=empty_text" not in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_body_length_limit_uses_max_body_length_constant(self):
        from retail.agents.domains.agent_webhook.services.direct_send_constants import (
            MAX_BODY_LENGTH,
        )

        self.assertEqual(MAX_BODY_LENGTH, 1024)
        template = _make_template(body="x" * MAX_BODY_LENGTH + " {{1}}")
        data = {
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:55",
        }
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self._build(template, data)
        self.assertIsNone(result)
        self.assertTrue(
            any("reason=component_length_limit" in line for line in captured.output),
            captured.output,
        )

    def test_length_check_runs_against_substituted_body_not_wire_key(self):
        """Length gate reads ``substituted_body`` pre-assembly. Anchor: FR-014d(e)."""
        long_body = "x" * 2048
        template = _make_template(body=long_body)
        data = {"template_variables": {}, "contact_urn": "whatsapp:55"}
        with self.assertLogs(_BUILDER_LOGGER, level=logging.WARNING) as captured:
            result = self._build(template, data)
        self.assertIsNone(result)
        self.assertTrue(
            any("reason=component_length_limit" in line for line in captured.output),
            captured.output,
        )
