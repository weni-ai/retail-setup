"""Tenant-isolation regression guard. Anchor: FR-040 / FR-042 / FR-045 / SC-010."""

from typing import Any, Dict
from unittest.mock import MagicMock
from uuid import uuid4

from django.core.cache import cache
from django.test import TestCase
from django.test.utils import override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_webhook.services.broadcast import Broadcast
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.broadcasts.models import BroadcastMessage
from retail.projects.models import Project
from retail.templates.models import Template, Version
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


_TEMPLATE_NAME = "weni_order_invoiced"
_LAMBDA_VARIABLES = {"1": "Maria"}


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "tenant-isolation",
        }
    }
)
class TenantIsolationRegressionTest(TestCase):
    """Cross-tenant invariants on the dispatch boundary.

    Two projects share the same Template ``name`` to surface any
    lookup that would accidentally cross-tenant scope.
    """

    def setUp(self):
        cache.clear()
        self.project_a, self.agent_a, self.ia_a, self.template_a = self._seed_project(
            name="Project A",
            vtex_account="store-a",
            ia_config={"direct_send": True},
            template_metadata={"body": "Hello {{1}}", "language": "pt_BR"},
        )
        self.project_b, self.agent_b, self.ia_b, self.template_b = self._seed_project(
            name="Project B",
            vtex_account="store-b",
            ia_config={},
            template_metadata={"language": "pt_BR"},
        )

        self.flows_service = MagicMock()
        self.flows_service.send_whatsapp_broadcast.side_effect = self._flows_response

        self.audit_calls = []

        def _capture_audit(path, data):
            self.audit_calls.append(data)

        self.audit_func = MagicMock(side_effect=_capture_audit)
        self.handler = Broadcast(
            flows_service=self.flows_service, audit_func=self.audit_func
        )

    def _flows_response(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Return a per-project broadcast id so the persisted rows pin
        the right project on each side.
        """
        if message["project"] == str(self.project_a.uuid):
            return {
                "id": 1001,
                "status": "queued",
                "metadata": {"template": {"uuid": str(uuid4())}},
            }
        return {
            "id": 2002,
            "status": "queued",
            "metadata": {"template": {"uuid": str(uuid4())}},
        }

    def _seed_project(
        self,
        *,
        name: str,
        vtex_account: str,
        ia_config: Dict[str, Any],
        template_metadata: Dict[str, Any],
    ):
        project = Project.objects.create(
            uuid=uuid4(), name=name, vtex_account=vtex_account
        )
        agent = Agent.objects.create(
            name=f"Agent {name}",
            lambda_arn=f"arn:aws:lambda:{vtex_account}",
            project=project,
            credentials={},
        )
        integrated_agent = IntegratedAgent.objects.create(
            agent=agent,
            project=project,
            channel_uuid=uuid4(),
            is_active=True,
            config=ia_config,
        )
        template = Template.objects.create(
            name=_TEMPLATE_NAME,
            integrated_agent=integrated_agent,
            metadata=template_metadata,
            is_active=True,
        )
        version = Version.objects.create(
            template=template,
            template_name=_TEMPLATE_NAME,
            integrations_app_uuid=uuid4(),
            project=project,
            status="APPROVED",
        )
        template.current_version = version
        template.save(update_fields=["current_version"])
        return project, agent, integrated_agent, template

    def _dispatch(self, integrated_agent: IntegratedAgent):
        lambda_data = {
            "template": _TEMPLATE_NAME,
            "template_variables": dict(_LAMBDA_VARIABLES),
            "contact_urn": "whatsapp:5598123456789",
        }
        message = self.handler.build_message(integrated_agent, lambda_data)
        self.assertIsNotNone(message)
        self.handler.send_message(message, integrated_agent, lambda_data)
        return message

    def test_broadcast_message_project_matches_integrated_agent_project(self):
        """``BroadcastMessage.project_id == integrated_agent.project_id``."""
        self._dispatch(self.ia_a)
        self._dispatch(self.ia_b)

        rows = list(
            BroadcastMessage.objects.select_related("integrated_agent").all()
        )
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(
                row.project_id,
                row.integrated_agent.project_id,
                "BroadcastMessage.project_id MUST match "
                "BroadcastMessage.integrated_agent.project_id. "
                f"Row: {row}",
            )

        project_ids = sorted(row.project_id for row in rows)
        self.assertEqual(
            project_ids, sorted([self.project_a.pk, self.project_b.pk])
        )

    def test_order_status_dedup_cache_key_carries_owning_project_id(self):
        """Dedup cache key scopes by owning project. Anchor: FR-040."""
        usecase = AgentOrderStatusUpdateUsecase()

        order_status_dto_a = OrderStatusDTO(
            recorder={},
            domain="orders",
            orderId="ORDER-A",
            currentState="invoiced",
            lastState="ready-for-handling",
            currentChangeDate="2026-05-21T10:00:00",
            lastChangeDate="2026-05-21T09:55:00",
            vtexAccount="store-a",
        )
        order_status_dto_b = OrderStatusDTO(
            recorder={},
            domain="orders",
            orderId="ORDER-B",
            currentState="invoiced",
            lastState="ready-for-handling",
            currentChangeDate="2026-05-21T10:00:00",
            lastChangeDate="2026-05-21T09:55:00",
            vtexAccount="store-b",
        )

        was_duplicate_a = usecase._is_duplicate_event(self.ia_a, order_status_dto_a)
        was_duplicate_b = usecase._is_duplicate_event(self.ia_b, order_status_dto_b)
        self.assertFalse(was_duplicate_a)
        self.assertFalse(was_duplicate_b)

        expected_key_a = (
            f"order_status_event:{self.ia_a.project_id}:{self.ia_a.uuid}:"
            f"ORDER-A:invoiced"
        )
        expected_key_b = (
            f"order_status_event:{self.ia_b.project_id}:{self.ia_b.uuid}:"
            f"ORDER-B:invoiced"
        )

        self.assertEqual(cache.get(expected_key_a), 1)
        self.assertEqual(cache.get(expected_key_b), 1)
        self.assertNotEqual(
            self.project_a.pk,
            self.project_b.pk,
            "Test setup precondition: project IDs must differ.",
        )

        cross_tenant_key_a_to_b = (
            f"order_status_event:{self.project_b.pk}:{self.ia_a.uuid}:"
            f"ORDER-A:invoiced"
        )
        cross_tenant_key_b_to_a = (
            f"order_status_event:{self.project_a.pk}:{self.ia_b.uuid}:"
            f"ORDER-B:invoiced"
        )
        self.assertIsNone(
            cache.get(cross_tenant_key_a_to_b),
            "Dedup cache key MUST NOT be writable under a peer tenant's "
            "project_id.",
        )
        self.assertIsNone(
            cache.get(cross_tenant_key_b_to_a),
            "Dedup cache key MUST NOT be writable under a peer tenant's "
            "project_id.",
        )

    def test_datalake_event_payload_carries_owning_project_uuid(self):
        """Datalake event tags owning project. Anchor: FR-042."""
        self._dispatch(self.ia_a)
        self._dispatch(self.ia_b)

        self.assertEqual(len(self.audit_calls), 2)
        for event in self.audit_calls:
            self.assertIn("project", event)
            self.assertIsInstance(event["project"], str)

        events_by_project = {event["project"]: event for event in self.audit_calls}
        self.assertIn(str(self.project_a.uuid), events_by_project)
        self.assertIn(str(self.project_b.uuid), events_by_project)
        self.assertEqual(
            events_by_project[str(self.project_a.uuid)]["agent"],
            str(self.agent_a.uuid),
        )
        self.assertEqual(
            events_by_project[str(self.project_b.uuid)]["agent"],
            str(self.agent_b.uuid),
        )

    def test_per_integrated_agent_template_lookup_is_tenant_scoped(self):
        """Template lookup is per-IntegratedAgent. Anchor: FR-045."""
        self.assertEqual(self.template_a.name, self.template_b.name)

        templates_a = list(
            self.ia_a.templates.filter(name=_TEMPLATE_NAME)
        )
        templates_b = list(
            self.ia_b.templates.filter(name=_TEMPLATE_NAME)
        )

        self.assertEqual(len(templates_a), 1)
        self.assertEqual(len(templates_b), 1)
        self.assertEqual(templates_a[0].pk, self.template_a.pk)
        self.assertEqual(templates_b[0].pk, self.template_b.pk)
        self.assertNotEqual(templates_a[0].pk, templates_b[0].pk)

        cross_tenant_lookup_a = self.ia_a.templates.filter(name=_TEMPLATE_NAME).filter(
            integrated_agent=self.ia_b
        )
        self.assertEqual(
            cross_tenant_lookup_a.count(),
            0,
            "Per-IntegratedAgent template lookup MUST NOT cross tenants.",
        )
