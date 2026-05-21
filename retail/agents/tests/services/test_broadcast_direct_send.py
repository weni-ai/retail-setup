"""Tests for ``Broadcast.build_direct_send_message`` (T011 cluster).

Covers Story 1 acceptance scenarios — happy-path wire shape (AS1 /
AS2 / AS3), quick-reply buttons (T011a), and the three Direct Send
refusal classes — naming-rule (T011b), empty-body /
component-length-limit (T011c), and the no-local-template edge case
that routes through ``Broadcast.build_message`` (T011d).

The audit-log shape pinned by these tests matches FR-039's
``[BroadcastDispatch] skipped_due_to_direct_send_validation: ...``
catalogue: ``project_uuid`` is the top-level key (FR-044), ``reason``
is one of ``{naming_rule, empty_body, component_length_limit}``.
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
    """Story 1 AS1 / AS2 / AS3 — happy-path wire shape (T011)."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def test_as1_body_with_two_variables_substituted_and_direct_send_flag(self):
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
        self.assertEqual(result["msg"]["template"]["name"], "weni_order_shipped")
        self.assertEqual(result["msg"]["template"]["locale"], "pt-BR")
        self.assertEqual(
            result["msg"]["body"], "Olá Maria, seu pedido 12345 foi enviado."
        )
        self.assertNotIn("variables", result["msg"]["template"])
        self.assertNotIn("buttons", result["msg"])
        self.assertNotIn("header", result["msg"])
        self.assertNotIn("attachments", result["msg"])

    def test_as2_image_header_and_cta_url_button(self):
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
        self.assertEqual(
            result["msg"]["buttons"],
            [
                {
                    "sub_type": "cta_url",
                    "display_text": "Acompanhar pedido",
                    "url": "https://loja.com/track/Maria",
                }
            ],
        )
        self.assertEqual(result["msg"]["body"], "Olá Maria, seu pedido 12345 chegou.")

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
            result["msg"]["body"], "Olá cliente, sua nota fiscal foi emitida."
        )
        self.assertNotIn("buttons", result["msg"])
        self.assertNotIn("header", result["msg"])
        self.assertNotIn("attachments", result["msg"])
        self.assertNotIn("footer", result["msg"])
        self.assertNotIn("variables", result["msg"]["template"])

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


class BuildDirectSendMessageQuickReplyButtonsTest(TestCase):
    """Quick-reply buttons rendering (T011a, contract §3.3)."""

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent()

    def test_three_quick_replies_with_substitution(self):
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
        result = self.handler.build_direct_send_message(
            data=data,
            channel_uuid=str(self.integrated_agent.channel_uuid),
            project_uuid=str(self.integrated_agent.project.uuid),
            template=template,
            integrated_agent=self.integrated_agent,
        )
        self.assertIsNotNone(result)
        buttons = result["msg"]["buttons"]
        self.assertEqual(len(buttons), 3)
        self.assertEqual(
            buttons,
            [
                {"sub_type": "reply", "id": "Sim, Maria", "title": "Sim, Maria"},
                {"sub_type": "reply", "id": "Não recebi", "title": "Não recebi"},
                {"sub_type": "reply", "id": "Ajuda", "title": "Ajuda"},
            ],
        )

    def test_substituted_title_within_length_limit_survives(self):
        template = _make_template(
            body="Body",
            buttons=[{"type": "QUICK_REPLY", "text": "Hi {{1}}"}],
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
        self.assertIsNotNone(result)
        self.assertEqual(result["msg"]["buttons"][0]["title"], "Hi Maria")


class BuildDirectSendMessageNamingRuleRefusalTest(TestCase):
    """FR-017 / Decision 7 — naming-rule refusal (T011b)."""

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
    """Defensive guard — caller did not provide ``contact_urn``.

    The rule engine MUST hand the recipient URN to dispatch; when it
    doesn't, ``build_direct_send_message`` logs an ERROR and returns
    ``None`` so no payload is emitted to Flows.
    """

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
        """``url`` is NOT length-checked at this gate (contract §3.3 —
        URLs can be much longer than the 20-char ``display_text`` ceiling).
        """
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
        self.assertEqual(result["msg"]["buttons"][0]["url"], long_url + "Maria")


class BuildMessageNoLocalTemplateEdgeCaseTest(TestCase):
    """Spec edge case — Direct Send-enabled agent with no local template (T011d).

    The dispatch must converge on the existing "template not found"
    skip path: ``build_direct_send_message`` is NOT invoked, no
    payload is built, no ``BroadcastMessage`` is persisted, and the
    legacy WARNING shape (preserved bit-for-bit per FR-027 / FR-039)
    is the only log line emitted.
    """

    def setUp(self):
        self.handler = Broadcast(flows_service=MagicMock(), audit_func=MagicMock())
        self.integrated_agent = _make_integrated_agent(direct_send=True)
        self.integrated_agent.templates.filter.return_value.first.return_value = None

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
