"""Tests for ``ListBroadcastDispatchesUseCase``."""

from datetime import datetime, timedelta, timezone as dt_timezone
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import (
    BroadcastConversion,
    BroadcastMessage,
    BroadcastStatus,
)
from retail.broadcasts.usecases.list_broadcast_dispatches import (
    ListBroadcastDispatchesDTO,
    ListBroadcastDispatchesUseCase,
)
from retail.projects.models import Project


class ListBroadcastDispatchesUseCaseTest(TestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.other_project = Project.objects.create(name="Project B", uuid=uuid4())
        self.agent = Agent.objects.create(name="Agent", project=self.project)
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.other_integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.use_case = ListBroadcastDispatchesUseCase()
        today = timezone.localdate()
        self.start_date = today - timedelta(days=1)
        self.end_date = today + timedelta(days=1)

    def _create_broadcast(self, *, project=None, **overrides):
        defaults = {
            "project": project or self.project,
            "integrated_agent": self.integrated_agent,
            "template_name": "payment_recovery",
            "contact_urn": "whatsapp:5511999999999",
            "status": BroadcastStatus.DELIVERED,
            "order_id": "order-1",
        }
        defaults.update(overrides)
        broadcast = BroadcastMessage.objects.create(**defaults)
        return broadcast

    def _execute(self, **overrides):
        dto = ListBroadcastDispatchesDTO(
            project_uuid=self.project.uuid,
            start_date=self.start_date,
            end_date=self.end_date,
            **overrides,
        )
        return self.use_case.execute(dto)

    def test_returns_dispatch_rows_with_conversion_metadata(self):
        broadcast = self._create_broadcast(order_id="order-conv")
        converted_at = timezone.now()
        conversion = BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=broadcast,
            order_id="order-conv",
        )
        BroadcastConversion.objects.filter(pk=conversion.pk).update(
            converted_at=converted_at
        )

        rows, total = self._execute()

        self.assertEqual(total, 1)
        row = rows[0]
        self.assertEqual(row.contact_urn, "whatsapp:5511999999999")
        self.assertEqual(row.order_id, "order-conv")
        self.assertEqual(row.status, BroadcastStatus.DELIVERED)
        self.assertTrue(row.converted)
        self.assertEqual(row.dispatched_at, broadcast.created_at)
        self.assertEqual(row.converted_at, converted_at)

    def test_marks_dispatch_as_not_converted_when_no_attribution(self):
        self._create_broadcast(order_id="order-no-conv")

        rows, total = self._execute()

        self.assertEqual(total, 1)
        self.assertFalse(rows[0].converted)
        self.assertIsNone(rows[0].converted_at)

    def test_filters_by_project_and_dispatch_date_range(self):
        in_range = self._create_broadcast(order_id="in-range")
        out_of_range = self._create_broadcast(order_id="out-range")
        BroadcastMessage.objects.filter(pk=out_of_range.pk).update(
            created_at=datetime.combine(
                self.start_date - timedelta(days=30),
                datetime.min.time(),
                tzinfo=dt_timezone.utc,
            )
        )
        other_project_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.other_project,
            channel_uuid=uuid4(),
        )
        self._create_broadcast(
            project=self.other_project,
            integrated_agent=other_project_agent,
            order_id="other-project",
        )

        rows, total = self._execute()

        self.assertEqual(total, 1)
        self.assertEqual(rows[0].order_id, in_range.order_id)

    def test_paginates_results(self):
        for index in range(3):
            broadcast = self._create_broadcast(
                contact_urn=f"whatsapp:551199999999{index}",
                order_id=f"order-{index}",
            )
            BroadcastMessage.objects.filter(pk=broadcast.pk).update(
                created_at=timezone.now() - timedelta(minutes=index)
            )

        rows, total = self._execute(page=2, page_size=1)

        self.assertEqual(total, 3)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].order_id, "order-1")

    def test_filters_by_integrated_agent_when_uuid_is_provided(self):
        self._create_broadcast(order_id="order-agent-a")
        self._create_broadcast(
            integrated_agent=self.other_integrated_agent,
            order_id="order-agent-b",
        )

        rows, total = self._execute(
            integrated_agent_uuid=self.integrated_agent.uuid,
        )

        self.assertEqual(total, 1)
        self.assertEqual(rows[0].order_id, "order-agent-a")
