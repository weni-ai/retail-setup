"""End-to-end Direct Send persistence parity. Anchor: FR-016."""

import logging

from typing import Any, Dict, List
from uuid import uuid4

from django.test import TestCase
from django.test.utils import override_settings

from unittest.mock import MagicMock

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.broadcasts.models import BroadcastMessage
from retail.projects.models import Project
from retail.templates.models import Template, Version


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "direct-send-persistence",
        }
    }
)
class BroadcastDirectSendPersistenceTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(), name="DirectSend Project", vtex_account="direct-send-store"
        )
        self.agent = Agent.objects.create(
            name="Order Status Agent",
            lambda_arn="arn:aws:lambda:direct-send",
            project=self.project,
            credentials={},
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            config={"direct_send": True},
        )
        self.template = self._create_template(
            name="weni_order_shipped",
            body="Olá {{1}}, seu pedido {{2}} foi enviado.",
            language="pt_BR",
        )
        self.flows_service = MagicMock()
        self.flows_service.send_whatsapp_broadcast.return_value = {
            "id": 4242,
            "status": "queued",
            "metadata": {"template": {"uuid": str(uuid4())}},
        }
        self.handler = Broadcast(
            flows_service=self.flows_service, audit_func=MagicMock()
        )
        self.lambda_data = {
            "template": "weni_order_shipped",
            "template_variables": {"1": "Maria", "2": "12345"},
            "contact_urn": "whatsapp:5598123456789",
        }

    def _create_template(
        self,
        *,
        name: str,
        body: str,
        language: str = "pt_BR",
        header: Dict[str, Any] = None,
        footer: str = None,
        buttons: List[Dict[str, Any]] = None,
    ) -> Template:
        metadata: Dict[str, Any] = {"body": body, "language": language}
        if header is not None:
            metadata["header"] = header
        if footer is not None:
            metadata["footer"] = footer
        if buttons is not None:
            metadata["buttons"] = buttons
        template = Template.objects.create(
            name=name,
            integrated_agent=self.integrated_agent,
            metadata=metadata,
            is_active=True,
        )
        version = Version.objects.create(
            template=template,
            template_name=name,
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        template.current_version = version
        template.save(update_fields=["current_version"])
        return template

    def test_happy_path_persists_broadcast_message(self):
        message = self.handler.build_message(self.integrated_agent, self.lambda_data)
        self.assertIsNotNone(message)
        self.assertIs(message["msg"]["direct_send"], True)

        self.handler.send_message(message, self.integrated_agent, self.lambda_data)

        rows = BroadcastMessage.objects.filter(integrated_agent=self.integrated_agent)
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.template_name, "weni_order_shipped")
        self.assertEqual(row.template_version, "weni_order_shipped")
        self.assertEqual(row.contact_urn, "whatsapp:5598123456789")
        self.assertEqual(row.integrated_agent_id, self.integrated_agent.pk)
        self.assertEqual(row.project_id, self.project.pk)
        self.assertEqual(row.broadcast_id, 4242)
        self.flows_service.send_whatsapp_broadcast.assert_called_once()

    def test_full_template_with_header_footer_buttons_persists_and_dispatches(self):
        """Realistic OrderStatus dispatch — image header + footer + CTA URL
        button. Pins ``quickstart.md §4.3`` end-to-end against the
        persistence path so a regression on any optional metadata branch
        (header / footer / buttons) of ``build_direct_send_message``
        surfaces as a persistence-parity failure.
        """
        Template.objects.all().delete()
        self._create_template(
            name="weni_order_invoiced",
            body="Olá {{1}}, sua nota fiscal do pedido {{2}} foi emitida.",
            header={"header_type": "IMAGE", "text": "image-placeholder"},
            footer="Acompanhe pelo app {{1}}.",
            buttons=[
                {
                    "type": "URL",
                    "text": "Acompanhar pedido",
                    "url": "https://loja.com/track/{{2}}",
                }
            ],
        )
        lambda_data = {
            "template": "weni_order_invoiced",
            "template_variables": {
                "1": "Maria",
                "2": "12345",
                "image_url": "https://cdn.loja.com/order_12345.jpg",
            },
            "contact_urn": "whatsapp:5598123456789",
        }

        message = self.handler.build_message(self.integrated_agent, lambda_data)
        self.assertIsNotNone(message)
        self.handler.send_message(message, self.integrated_agent, lambda_data)

        outbound = self.flows_service.send_whatsapp_broadcast.call_args.args[0]
        msg = outbound["msg"]
        self.assertEqual(
            msg["text"], "Olá Maria, sua nota fiscal do pedido 12345 foi emitida."
        )
        self.assertNotIn("body", msg)
        self.assertEqual(msg["direct_send_template_name"], "weni_order_invoiced")
        self.assertNotIn("template", msg)
        self.assertNotIn("locale", msg)
        self.assertNotIn("language", msg)
        self.assertEqual(
            msg["header"],
            {"type": "image", "image_url": "https://cdn.loja.com/order_12345.jpg"},
        )
        self.assertEqual(msg["footer"], "Acompanhe pelo app Maria.")
        self.assertEqual(msg["interaction_type"], "cta_url")
        self.assertEqual(
            msg["cta_message"],
            {
                "display_text": "Acompanhar pedido",
                "url": "https://loja.com/track/12345",
            },
        )
        self.assertNotIn("buttons", msg)
        self.assertEqual(
            msg["attachments"],
            ["image/jpeg:https://cdn.loja.com/order_12345.jpg"],
        )

        rows = BroadcastMessage.objects.filter(integrated_agent=self.integrated_agent)
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.template_name, "weni_order_invoiced")
        self.assertEqual(row.contact_urn, "whatsapp:5598123456789")
        self.assertEqual(row.project_id, self.project.pk)

    def test_naming_rule_refusal_does_not_persist(self):
        Template.objects.all().delete()
        self._create_template(
            name="Weni_Order_Shipped",
            body="Olá {{1}}.",
        )
        with self.assertLogs(
            "retail.agents.domains.agent_webhook.services.broadcast",
            level=logging.WARNING,
        ) as captured:
            message = self.handler.build_message(
                self.integrated_agent,
                {
                    "template": "Weni_Order_Shipped",
                    "template_variables": {"1": "Maria"},
                    "contact_urn": "whatsapp:55",
                },
            )
        self.assertIsNone(message)
        self.flows_service.send_whatsapp_broadcast.assert_not_called()
        self.assertFalse(
            BroadcastMessage.objects.filter(
                integrated_agent=self.integrated_agent
            ).exists()
        )
        self.assertTrue(
            any(
                "skipped_due_to_direct_send_validation" in line
                and "reason=naming_rule" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_empty_body_refusal_does_not_persist(self):
        Template.objects.all().delete()
        self._create_template(name="weni_order_empty", body="")
        with self.assertLogs(
            "retail.agents.domains.agent_webhook.services.broadcast",
            level=logging.WARNING,
        ) as captured:
            message = self.handler.build_message(
                self.integrated_agent,
                {
                    "template": "weni_order_empty",
                    "template_variables": {},
                    "contact_urn": "whatsapp:55",
                },
            )
        self.assertIsNone(message)
        self.flows_service.send_whatsapp_broadcast.assert_not_called()
        self.assertFalse(
            BroadcastMessage.objects.filter(
                integrated_agent=self.integrated_agent
            ).exists()
        )
        self.assertTrue(
            any(
                "skipped_due_to_direct_send_validation" in line
                and "reason=empty_body" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_length_limit_refusal_does_not_persist(self):
        Template.objects.all().delete()
        self._create_template(
            name="weni_order_long",
            body="x" * 1024 + " {{1}}",
        )
        with self.assertLogs(
            "retail.agents.domains.agent_webhook.services.broadcast",
            level=logging.WARNING,
        ) as captured:
            message = self.handler.build_message(
                self.integrated_agent,
                {
                    "template": "weni_order_long",
                    "template_variables": {"1": "Maria"},
                    "contact_urn": "whatsapp:55",
                },
            )
        self.assertIsNone(message)
        self.flows_service.send_whatsapp_broadcast.assert_not_called()
        self.assertFalse(
            BroadcastMessage.objects.filter(
                integrated_agent=self.integrated_agent
            ).exists()
        )
        self.assertTrue(
            any(
                "skipped_due_to_direct_send_validation" in line
                and "reason=component_length_limit" in line
                for line in captured.output
            ),
            captured.output,
        )

    def test_template_metadata_body_storage_key_is_preserved(self):
        """``Template.metadata["body"]`` is wire-rename-immune. Anchor: FR-014d(c)."""
        self.assertEqual(
            self.template.metadata["body"],
            "Olá {{1}}, seu pedido {{2}} foi enviado.",
        )
        self.assertNotIn("text", self.template.metadata)

    def test_send_message_log_line_carries_direct_send_template_name(self):
        """Path-aware logging accessor after wire-shape change. Anchor: FR-014c."""
        message = self.handler.build_message(self.integrated_agent, self.lambda_data)
        self.assertIsNotNone(message)

        with self.assertLogs(
            "retail.agents.domains.agent_webhook.services.broadcast",
            level=logging.INFO,
        ) as captured:
            self.handler.send_message(message, self.integrated_agent, self.lambda_data)

        joined = "\n".join(captured.output)
        self.assertIn("weni_order_shipped", joined)
        self.assertNotIn("Template: unknown", joined)
