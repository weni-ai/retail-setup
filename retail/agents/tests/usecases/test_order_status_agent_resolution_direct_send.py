"""FR-031 official-agent precedence regression on the Direct Send
cohort (T014b).

When the order-status resolution finds BOTH an official agent
(matched on ``settings.ORDER_STATUS_AGENT_UUID``) AND a custom agent
with ``parent_agent_uuid`` for the same project, the official agent
MUST take precedence — a single event MUST NEVER dispatch through
both agents simultaneously. This regression test pins that contract
specifically for the Direct Send cohort.
"""

import logging

from typing import Any, Dict
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings

from unittest.mock import MagicMock, patch

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.active_agent import ActiveAgent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.agents.domains.agent_webhook.usecases.webhook import AgentWebhookUseCase
from retail.broadcasts.models import BroadcastMessage
from retail.projects.models import Project
from retail.templates.models import Template, Version
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "direct-send-agent-resolution",
        }
    }
)
class OrderStatusAgentResolutionOnDirectSendTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="DS Resolution Project",
            vtex_account="ds-resolution-store",
        )

        self.official_agent_uuid = uuid4()
        self.official_agent = Agent.objects.create(
            uuid=self.official_agent_uuid,
            name="Official OrderStatus",
            lambda_arn="arn:aws:lambda:official",
            project=self.project,
            is_oficial=True,
            credentials={},
        )
        self.custom_agent = Agent.objects.create(
            name="Custom OrderStatus",
            lambda_arn="arn:aws:lambda:custom",
            project=self.project,
            is_oficial=False,
            credentials={},
        )

        self.official_integrated = IntegratedAgent.objects.create(
            agent=self.official_agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            contact_percentage=100,
            config={"direct_send": True},
        )
        self.custom_integrated = IntegratedAgent.objects.create(
            agent=self.custom_agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            contact_percentage=100,
            config={"direct_send": True},
            parent_agent_uuid=self.official_agent_uuid,
        )

        self._create_template(self.official_integrated)
        self._create_template(self.custom_integrated)

        self.flows_service = MagicMock()
        self.flows_service.send_whatsapp_broadcast.return_value = {
            "id": 9999,
            "status": "queued",
            "metadata": {"template": {"uuid": str(uuid4())}},
        }

        self.lambda_payload: Dict[str, Any] = {
            "template": "weni_order_invoiced",
            "template_variables": {"1": "Maria"},
            "contact_urn": "whatsapp:5598123456789",
            "status": 0,
        }
        self.active_agent = MagicMock(spec=ActiveAgent)
        self.active_agent.invoke.return_value = {"Payload": MagicMock()}
        self.active_agent.parse_response.return_value = self.lambda_payload
        self.active_agent.validate_response.return_value = True

        self.cache_handler = MagicMock()
        self.cache_handler.get_role_agent.return_value = None
        self.cache_handler.get_cached_agent.return_value = None
        self.usecase = AgentOrderStatusUpdateUsecase(cache_handler=self.cache_handler)

        self.order_status_dto = MagicMock(spec=OrderStatusDTO)
        self.order_status_dto.orderId = "11111-01"
        self.order_status_dto.currentState = "invoiced"
        self.order_status_dto.lastState = "ready-for-handling"
        self.order_status_dto.domain = "Marketplace"
        self.order_status_dto.vtexAccount = self.project.vtex_account

    def _create_template(self, integrated_agent: IntegratedAgent) -> None:
        template = Template.objects.create(
            name="weni_order_invoiced",
            integrated_agent=integrated_agent,
            metadata={
                "body": "Olá {{1}}, sua nota fiscal foi emitida.",
                "language": "pt_BR",
            },
            is_active=True,
        )
        version = Version.objects.create(
            template=template,
            template_name="weni_order_invoiced",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        template.current_version = version
        template.save(update_fields=["current_version"])

    def _build_webhook_factory(self):
        broadcast = Broadcast(flows_service=self.flows_service, audit_func=MagicMock())
        webhook = AgentWebhookUseCase(
            active_agent=self.active_agent,
            broadcast=broadcast,
            cache=self.cache_handler,
        )
        return lambda *_args, **_kwargs: webhook

    def test_official_agent_wins_over_parent_flagged_custom_agent(self):
        with override_settings(ORDER_STATUS_AGENT_UUID=str(self.official_agent_uuid)):
            with patch(
                "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase",
                side_effect=self._build_webhook_factory(),
            ):
                resolved = self.usecase.get_integrated_agent_if_exists(self.project)
                self.usecase.execute(resolved, self.order_status_dto)

        self.assertEqual(resolved.pk, self.official_integrated.pk)
        self.flows_service.send_whatsapp_broadcast.assert_called_once()
        rows = BroadcastMessage.objects.all()
        self.assertEqual(rows.count(), 1)
        row = rows.first()
        self.assertEqual(row.integrated_agent_id, self.official_integrated.pk)
        self.assertNotEqual(row.integrated_agent_id, self.custom_integrated.pk)

    def test_resolution_log_carries_official_source_discriminator(self):
        with override_settings(ORDER_STATUS_AGENT_UUID=str(self.official_agent_uuid)):
            with self.assertLogs(
                "retail.agents.domains.agent_webhook.usecases.order_status",
                level=logging.INFO,
            ) as captured:
                self.usecase.get_integrated_agent_if_exists(self.project)

        admission_substrings = [
            "[ORDER_STATUS] agent_resolved",
            f"vtex_account={self.project.vtex_account}",
            f"agent_uuid={self.official_integrated.uuid}",
            "source=official",
        ]
        self.assertTrue(
            any(
                all(sub in line for sub in admission_substrings)
                for line in captured.output
            ),
            captured.output,
        )
        self.assertFalse(
            any("source=parent_agent" in line for line in captured.output),
            captured.output,
        )
