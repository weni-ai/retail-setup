"""End-to-end Direct Send persistence parity (T011e — FR-016 / SC-005).

Drives ``Broadcast.build_message`` → ``Broadcast.send_message`` against
a Direct Send-enabled fixture and asserts:

- the happy path persists exactly one ``BroadcastMessage`` row with
  the expected fields,
- each Direct Send refusal class (naming-rule, empty body, length
  limit) skips persistence entirely (no row written).

``flows_service.send_whatsapp_broadcast`` is mocked at the boundary
so the test captures the outbound payload without hitting Flows.
"""

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
