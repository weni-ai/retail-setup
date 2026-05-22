"""FR-028 / FR-029 / FR-030 / FR-039 dedup regression on the Direct
Send cohort (T014a + T014c + T014d).

Pins the canonical idempotency tuple
``(project, integrated_agent.uuid, order_id, current_state)`` on the
Direct Send path:

- Two invocations with the same tuple collapse into ONE outbound
  Flows POST and ONE ``BroadcastMessage`` row (T014a).
- The second invocation emits the documented ``duplicate_skipped``
  INFO log shape (FR-039, T014a).
- The cache key matches the five-segment shape pinned by FR-029
  (T014a).
- Two invocations sharing ``(project, agent, order_id)`` but differing
  in ``current_state`` MUST dispatch as TWO distinct logical broadcasts
  (FR-030, T014c). Direct counter-evidence that the dedup gate keys on
  ``current_state`` — a refactor dropping that component from the key
  would silently merge two distinct logical broadcasts into one and
  fail this test.
- The unpause race (PAUSED → APPROVED flip during the dedup window of
  an in-flight broadcast for the same template) MUST NOT auto-replay —
  the dedup cache key was populated by the original PAUSED-skip
  attempt, and the subsequent webhook (within the dedup window) skips
  via the FR-028 duplicate-skip gate even though the version status is
  now APPROVED (T014d). Pins the spec Edge Case "an event that arrived
  during the dedup window of an earlier PAUSED-skip will NOT
  auto-replay; the next webhook is the trigger".

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

    def test_different_current_state_dispatches_as_distinct_logical_broadcasts(self):
        """FR-030 (T014c): two events differing ONLY in ``current_state``
        MUST both dispatch as separate logical broadcasts.

        Same ``(project, integrated_agent.uuid, order_id)`` triple,
        different ``current_state`` values → distinct dedup cache keys
        → both pass the dedup gate → two outbound Flows POSTs → two
        ``BroadcastMessage`` rows. ``BroadcastMessage`` does not store
        ``current_state`` directly (the column is absent on the model,
        see ``retail/broadcasts/models.py``); the two rows are matched
        to their originating invocations via the distinct ``broadcast_id``
        values returned by the Flows mock. The shared ``order_id``
        confirms both rows belong to the same physical order.
        """
        self.flows_service.send_whatsapp_broadcast.side_effect = [
            {
                "id": 9001,
                "status": "queued",
                "metadata": {"template": {"uuid": str(uuid4())}},
            },
            {
                "id": 9002,
                "status": "queued",
                "metadata": {"template": {"uuid": str(uuid4())}},
            },
        ]

        second_dto = MagicMock(spec=OrderStatusDTO)
        second_dto.orderId = self.order_status_dto.orderId
        second_dto.currentState = "shipped"
        second_dto.lastState = "invoiced"
        second_dto.domain = "Marketplace"
        second_dto.vtexAccount = self.project.vtex_account

        captured_keys: List[str] = []
        original_cache_add = cache.add

        def _wrapped_add(key, *args, **kwargs):
            captured_keys.append(key)
            return original_cache_add(key, *args, **kwargs)

        webhook_factory = self._build_webhook_factory()
        with patch(
            "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase",
            side_effect=lambda *_a, **_kw: webhook_factory(),
        ), patch(
            "retail.agents.domains.agent_webhook.usecases.order_status.cache.add",
            side_effect=_wrapped_add,
        ):
            self.usecase.execute(self.integrated_agent, self.order_status_dto)
            self.usecase.execute(self.integrated_agent, second_dto)

        self.assertEqual(
            self.flows_service.send_whatsapp_broadcast.call_count,
            2,
            "expected two outbound Flows POSTs — one per distinct current_state",
        )

        persisted_rows = BroadcastMessage.objects.filter(
            integrated_agent=self.integrated_agent
        )
        self.assertEqual(persisted_rows.count(), 2)
        persisted_broadcast_ids = sorted(
            persisted_rows.values_list("broadcast_id", flat=True)
        )
        self.assertEqual(persisted_broadcast_ids, [9001, 9002])
        persisted_order_ids = set(persisted_rows.values_list("order_id", flat=True))
        self.assertEqual(persisted_order_ids, {self.order_status_dto.orderId})

        self.assertEqual(len(captured_keys), 2, captured_keys)
        self.assertNotEqual(captured_keys[0], captured_keys[1])
        first_segments = captured_keys[0].split(":")
        second_segments = captured_keys[1].split(":")
        self.assertEqual(len(first_segments), 5)
        self.assertEqual(len(second_segments), 5)
        self.assertEqual(first_segments[:4], second_segments[:4])
        self.assertEqual(first_segments[4], "invoiced")
        self.assertEqual(second_segments[4], "shipped")

    def test_unpause_race_within_dedup_window_does_not_auto_replay(self):
        """T014d / spec Edge Case — PAUSED → APPROVED flip during the
        dedup window of an in-flight broadcast for the same template
        MUST NOT auto-replay.

        Steps:
        1. Template ``current_version.status`` starts at ``PAUSED``.
        2. Invoke ``execute(...)`` once → dispatch is skipped via the
           FR-039 unified ``[BroadcastDispatch] skipped_due_to_status``
           audit shape; the dedup cache key IS populated (the dedup
           gate accepted the event BEFORE the version-status read).
        3. Flip the version status to ``APPROVED`` (simulating the
           unpause race).
        4. Invoke ``execute(...)`` again with the SAME canonical
           idempotency tuple — the dedup gate now skips the event
           via the FR-028 ``[ORDER_STATUS] duplicate_skipped`` audit
           shape; no Flows POST and no ``BroadcastMessage`` row.

        Pins the spec edge case "an event that arrived during the
        dedup window of an earlier PAUSED-skip will NOT auto-replay;
        the next webhook is the trigger" against a future refactor
        that moved the version-status read BEFORE the dedup cache
        write (which would silently re-fire the dispatch on unpause).
        """
        version = Version.objects.get(template__name="weni_order_shipped")
        version.status = "PAUSED"
        version.save(update_fields=["status"])

        webhook_factory = self._build_webhook_factory()
        with patch(
            "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase",
            side_effect=lambda *_a, **_kw: webhook_factory(),
        ):
            with self.assertLogs(
                "retail.agents.domains.agent_webhook.services.broadcast",
                level=logging.WARNING,
            ) as paused_logs:
                self.usecase.execute(self.integrated_agent, self.order_status_dto)

        self.flows_service.send_whatsapp_broadcast.assert_not_called()
        self.assertFalse(
            BroadcastMessage.objects.filter(
                integrated_agent=self.integrated_agent
            ).exists()
        )
        expected_paused_substrings = [
            "[BroadcastDispatch] skipped_due_to_status",
            f"project_uuid={self.project.uuid}",
            "template=weni_order_shipped",
            "version_status=PAUSED",
        ]
        self.assertTrue(
            any(
                all(sub in line for sub in expected_paused_substrings)
                for line in paused_logs.output
            ),
            paused_logs.output,
        )

        version.status = "APPROVED"
        version.save(update_fields=["status"])

        with patch(
            "retail.agents.domains.agent_webhook.usecases.order_status.AgentWebhookUseCase",
            side_effect=lambda *_a, **_kw: webhook_factory(),
        ):
            with self.assertLogs(
                "retail.agents.domains.agent_webhook.usecases.order_status",
                level=logging.INFO,
            ) as dedup_logs:
                self.usecase.execute(self.integrated_agent, self.order_status_dto)

        self.flows_service.send_whatsapp_broadcast.assert_not_called()
        self.assertFalse(
            BroadcastMessage.objects.filter(
                integrated_agent=self.integrated_agent
            ).exists()
        )
        expected_dedup_substrings = [
            "[ORDER_STATUS] duplicate_skipped",
            f"vtex_account={self.project.vtex_account}",
            f"agent_uuid={self.integrated_agent.uuid}",
            "current_state=invoiced",
            "order_id=12345-01",
        ]
        self.assertTrue(
            any(
                all(sub in line for sub in expected_dedup_substrings)
                for line in dedup_logs.output
            ),
            dedup_logs.output,
        )
