"""FR-028 / FR-029 / FR-030 / FR-039 dedup regression on the Direct
Send cohort (T014a).

Pins the canonical idempotency tuple
``(project, integrated_agent.uuid, order_id, current_state)`` on the
Direct Send path:

- Two invocations with the same tuple collapse into ONE outbound
  Flows POST and ONE ``BroadcastMessage`` row.
- The second invocation emits the documented ``duplicate_skipped``
  INFO log shape (FR-039).
- The cache key matches the five-segment shape pinned by FR-029.

The legacy cohort is already covered by the pre-feature dedup tests
in ``test_order_status_update.py``; this file is the Direct
Send-specific regression guard that runs alongside them.
"""

import logging

from typing import List
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
            "LOCATION": "direct-send-dedup",
        }
    }
)
class OrderStatusDedupOnDirectSendTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(
            uuid=uuid4(), name="DS Dedup Project", vtex_account="ds-dedup-store"
        )
        self.agent = Agent.objects.create(
            name="Order Status Agent",
            lambda_arn="arn:aws:lambda:ds-dedup",
            project=self.project,
            credentials={},
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            contact_percentage=100,
            config={"direct_send": True},
        )
        self._create_template()

        self.flows_service = MagicMock()
        self.flows_service.send_whatsapp_broadcast.return_value = {
            "id": 4242,
            "status": "queued",
            "metadata": {"template": {"uuid": str(uuid4())}},
        }

        self.lambda_payload = {
            "template": "weni_order_shipped",
            "template_variables": {"1": "Maria", "2": "12345"},
            "contact_urn": "whatsapp:5598123456789",
            "status": 0,
        }
        self.active_agent = MagicMock(spec=ActiveAgent)
        self.active_agent.invoke.return_value = {"Payload": MagicMock()}
        self.active_agent.parse_response.return_value = self.lambda_payload
        self.active_agent.validate_response.return_value = True

        self.cache_handler = MagicMock()
        self.cache_handler.get_role_agent.return_value = self.integrated_agent
        self.cache_handler.get_cached_agent.return_value = self.integrated_agent
        self.usecase = AgentOrderStatusUpdateUsecase(cache_handler=self.cache_handler)

        self.order_status_dto = MagicMock(spec=OrderStatusDTO)
        self.order_status_dto.orderId = "12345-01"
        self.order_status_dto.currentState = "invoiced"
        self.order_status_dto.lastState = "ready-for-handling"
        self.order_status_dto.domain = "Marketplace"
        self.order_status_dto.vtexAccount = self.project.vtex_account

    def _create_template(self) -> None:
        template = Template.objects.create(
            name="weni_order_shipped",
            integrated_agent=self.integrated_agent,
            metadata={
                "body": "Olá {{1}}, seu pedido {{2}} foi enviado.",
                "language": "pt_BR",
            },
            is_active=True,
        )
        version = Version.objects.create(
            template=template,
            template_name="weni_order_shipped",
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
        return lambda: webhook

    def test_duplicate_tuple_collapses_to_one_dispatch_and_one_row(self):
        webhook_factory = self._build_webhook_factory()
        with patch(
            "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase",
            side_effect=lambda *_a, **_kw: webhook_factory(),
        ):
            self.usecase.execute(self.integrated_agent, self.order_status_dto)
            with self.assertLogs(
                "retail.agents.domains.agent_webhook.usecases.order_status",
                level=logging.INFO,
            ) as captured:
                self.usecase.execute(self.integrated_agent, self.order_status_dto)

        self.flows_service.send_whatsapp_broadcast.assert_called_once()
        self.assertEqual(
            BroadcastMessage.objects.filter(
                integrated_agent=self.integrated_agent
            ).count(),
            1,
        )
        expected_log_substrings = [
            "[ORDER_STATUS] duplicate_skipped",
            f"vtex_account={self.project.vtex_account}",
            f"agent_uuid={self.integrated_agent.uuid}",
            "current_state=invoiced",
            "order_id=12345-01",
        ]
        self.assertTrue(
            any(
                all(sub in line for sub in expected_log_substrings)
                for line in captured.output
            ),
            captured.output,
        )

    def test_dedup_cache_key_carries_canonical_five_segments(self):
        captured_keys: List[str] = []
        original_cache_add = cache.add

        def _wrapped_add(key, *args, **kwargs):
            captured_keys.append(key)
            return original_cache_add(key, *args, **kwargs)

        webhook_factory = self._build_webhook_factory()
        fresh_dto = MagicMock(spec=OrderStatusDTO)
        fresh_dto.orderId = "fresh-order-9999"
        fresh_dto.currentState = "shipped"
        fresh_dto.lastState = "invoiced"
        fresh_dto.domain = "Marketplace"
        fresh_dto.vtexAccount = self.project.vtex_account

        with patch(
            "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase",
            side_effect=lambda *_a, **_kw: webhook_factory(),
        ), patch(
            "retail.agents.domains.agent_webhook.usecases.order_status.cache.add",
            side_effect=_wrapped_add,
        ):
            self.usecase.execute(self.integrated_agent, fresh_dto)

        self.assertEqual(len(captured_keys), 1, captured_keys)
        cache_key = captured_keys[0]
        pattern = r"^order_status_event:[^:]+:[0-9a-f-]{36}:[^:]+:[^:]+$"
        self.assertRegex(cache_key, pattern)
        segments = cache_key.split(":")
        self.assertEqual(
            len(segments),
            5,
            f"expected exactly 5 segments in {cache_key!r}, got {len(segments)}",
        )
        self.assertEqual(segments[0], "order_status_event")
        self.assertEqual(segments[2], str(self.integrated_agent.uuid))
        self.assertEqual(segments[3], "fresh-order-9999")
        self.assertEqual(segments[4], "shipped")
