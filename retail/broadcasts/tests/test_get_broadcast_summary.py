"""Tests for ``GetBroadcastSummaryUseCase``."""

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
from retail.broadcasts.usecases.get_broadcast_summary import (
    GetBroadcastSummaryDTO,
    GetBroadcastSummaryUseCase,
)
from retail.projects.models import Project


class GetBroadcastSummaryUseCaseTest(TestCase):
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
        self.use_case = GetBroadcastSummaryUseCase()
        today = timezone.localdate()
        self.start_date = today - timedelta(days=1)
        self.end_date = today + timedelta(days=1)

    def _create_broadcast(
        self, *, integrated_agent=None, status=BroadcastStatus.DELIVERED, **overrides
    ):
        defaults = {
            "project": self.project,
            "integrated_agent": integrated_agent or self.integrated_agent,
            "template_name": "payment_recovery",
            "contact_urn": "whatsapp:5511999999999",
            "status": status,
            "order_id": "order-1",
        }
        defaults.update(overrides)
        return BroadcastMessage.objects.create(**defaults)

    def _execute(self, **overrides):
        dto = GetBroadcastSummaryDTO(
            project_uuid=self.project.uuid,
            integrated_agent_uuid=self.integrated_agent.uuid,
            start_date=self.start_date,
            end_date=self.end_date,
            **overrides,
        )
        return self.use_case.execute(dto)

    def test_counts_delivered_and_converted_for_agent(self):
        broadcast = self._create_broadcast(status=BroadcastStatus.DELIVERED)
        self._create_broadcast(
            integrated_agent=self.integrated_agent,
            status=BroadcastStatus.READ,
            order_id="order-2",
        )
        self._create_broadcast(
            integrated_agent=self.integrated_agent,
            status=BroadcastStatus.SENT,
            order_id="order-3",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=broadcast,
            order_id="order-1",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="order-4",
        )

        result = self._execute()

        self.assertEqual(result.delivered, 2)
        self.assertEqual(result.converted, 2)

    def test_excludes_other_agents_and_out_of_range_rows(self):
        self._create_broadcast(status=BroadcastStatus.DELIVERED)
        self._create_broadcast(
            integrated_agent=self.other_integrated_agent,
            status=BroadcastStatus.DELIVERED,
            order_id="other-agent",
        )
        out_of_range = self._create_broadcast(
            status=BroadcastStatus.DELIVERED,
            order_id="old-order",
        )
        BroadcastMessage.objects.filter(pk=out_of_range.pk).update(
            created_at=datetime.combine(
                self.start_date - timedelta(days=30),
                datetime.min.time(),
                tzinfo=dt_timezone.utc,
            )
        )
        conversion = BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="order-conv",
        )
        BroadcastConversion.objects.filter(pk=conversion.pk).update(
            converted_at=datetime.combine(
                self.start_date - timedelta(days=29),
                datetime.min.time(),
                tzinfo=dt_timezone.utc,
            )
        )

        result = self._execute()

        self.assertEqual(result.delivered, 1)
        self.assertEqual(result.converted, 0)

    def test_aggregates_all_agents_when_integrated_agent_uuid_is_omitted(self):
        self._create_broadcast(
            integrated_agent=self.integrated_agent,
            status=BroadcastStatus.DELIVERED,
            order_id="order-a",
        )
        self._create_broadcast(
            integrated_agent=self.other_integrated_agent,
            status=BroadcastStatus.READ,
            order_id="order-b",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="order-a",
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.other_integrated_agent,
            order_id="order-b",
        )

        dto = GetBroadcastSummaryDTO(
            project_uuid=self.project.uuid,
            start_date=self.start_date,
            end_date=self.end_date,
        )
        result = self.use_case.execute(dto)

        self.assertEqual(result.delivered, 2)
        self.assertEqual(result.converted, 2)
