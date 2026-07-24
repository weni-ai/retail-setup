"""Tests for ``GetPaymentRecoveryConversionMetricsUseCase``."""

from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from uuid import uuid4

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.broadcasts.models import (
    BroadcastConversion,
    BroadcastMessage,
    BroadcastStatus,
)
from retail.broadcasts.usecases.get_payment_recovery_conversion_metrics import (
    CACHE_KEY_TEMPLATE,
    CURRENT_DAY_CACHE_TTL_SECONDS,
    HISTORICAL_CACHE_TTL_SECONDS,
    GetPaymentRecoveryConversionMetricsDTO,
    GetPaymentRecoveryConversionMetricsUseCase,
)
from retail.projects.models import Project

PAYMENT_RECOVERY_AGENT_UUID = str(uuid4())
OTHER_AGENT_UUID = str(uuid4())


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "payment-recovery-metrics-tests",
        }
    },
    PAYMENT_RECOVERY_AGENT_UUID=PAYMENT_RECOVERY_AGENT_UUID,
)
class GetPaymentRecoveryConversionMetricsUseCaseTest(TestCase):
    def setUp(self):
        cache.clear()
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.other_project = Project.objects.create(name="Project B", uuid=uuid4())
        self.payment_recovery_agent = Agent.objects.create(
            uuid=PAYMENT_RECOVERY_AGENT_UUID,
            name="Whatsapp Payment Recovery",
            slug="payment-recovery",
            description="",
            project=self.project,
        )
        self.other_agent = Agent.objects.create(
            uuid=OTHER_AGENT_UUID,
            name="Abandoned Cart",
            slug="abandoned-cart",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.payment_recovery_agent,
            project=self.project,
            channel_uuid=uuid4(),
            config={"payment_recovery": {"delay_minutes": 5}},
        )
        self.other_integrated_agent = IntegratedAgent.objects.create(
            agent=self.payment_recovery_agent,
            project=self.project,
            channel_uuid=uuid4(),
            config={"payment_recovery": {"delay_minutes": 10}},
        )
        self.non_payment_recovery_integrated_agent = IntegratedAgent.objects.create(
            agent=self.other_agent,
            project=self.project,
            channel_uuid=uuid4(),
        )
        self.use_case = GetPaymentRecoveryConversionMetricsUseCase()
        today = timezone.localdate()
        self.start_date = today - timedelta(days=1)
        self.end_date = today + timedelta(days=1)

    def tearDown(self):
        cache.clear()

    def _create_broadcast(
        self,
        *,
        integrated_agent=None,
        status=BroadcastStatus.DELIVERED,
        **overrides,
    ):
        defaults = {
            "project": self.project,
            "integrated_agent": integrated_agent or self.integrated_agent,
            "template_name": "payment_recovery",
            "contact_urn": "whatsapp:5511999999999",
            "status": status,
            "order_id": f"order-{uuid4()}",
        }
        defaults.update(overrides)
        return BroadcastMessage.objects.create(**defaults)

    def _execute(self, **overrides):
        dto = GetPaymentRecoveryConversionMetricsDTO(
            project_uuid=self.project.uuid,
            start_date=self.start_date,
            end_date=self.end_date,
            **overrides,
        )
        return self.use_case.execute(dto)

    def test_returns_conversion_metrics_for_payment_recovery_dispatches(self):
        broadcast_one = self._create_broadcast(status=BroadcastStatus.DELIVERED)
        broadcast_two = self._create_broadcast(
            integrated_agent=self.integrated_agent,
            status=BroadcastStatus.SENT,
            order_id="order-sent",
        )
        self._create_broadcast(status=BroadcastStatus.QUEUED, order_id="order-queued")
        self._create_broadcast(status=BroadcastStatus.FAILED, order_id="order-failed")
        self._create_broadcast(
            integrated_agent=self.non_payment_recovery_integrated_agent,
            status=BroadcastStatus.DELIVERED,
            order_id="order-other-agent",
        )

        converted_at = timezone.now()
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=broadcast_one,
            order_id=broadcast_one.order_id,
            value=Decimal("100.00"),
            converted_at=converted_at,
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=broadcast_two,
            order_id=broadcast_two.order_id,
            value=Decimal("200.00"),
            converted_at=converted_at + timedelta(hours=1),
        )

        result = self._execute()

        self.assertEqual(result.total_dispatches, 2)
        self.assertEqual(result.converted_payments, 2)
        self.assertEqual(result.conversion_rate, Decimal("100.00"))
        self.assertEqual(result.recovered_revenue, Decimal("300.00"))
        self.assertEqual(result.average_ticket, Decimal("150.00"))
        self.assertIsNotNone(result.first_conversion_at)
        self.assertIsNotNone(result.last_conversion_at)
        self.assertLessEqual(result.first_conversion_at, result.last_conversion_at)

    def test_excludes_other_agents_and_out_of_range_rows(self):
        self._create_broadcast(status=BroadcastStatus.DELIVERED)
        self._create_broadcast(
            integrated_agent=self.other_integrated_agent,
            status=BroadcastStatus.DELIVERED,
            order_id="other-delay",
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

        result = self._execute(integrated_agent_uuid=self.integrated_agent.uuid)

        self.assertEqual(result.total_dispatches, 1)
        self.assertEqual(result.converted_payments, 0)
        self.assertEqual(result.conversion_rate, Decimal("0"))
        self.assertEqual(result.recovered_revenue, Decimal("0"))
        self.assertIsNone(result.average_ticket)

    def test_aggregates_all_payment_recovery_agents_when_uuid_is_omitted(self):
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

        result = self._execute()

        self.assertEqual(result.total_dispatches, 2)

    def test_returns_zeros_when_payment_recovery_agent_is_not_configured(self):
        with override_settings(PAYMENT_RECOVERY_AGENT_UUID=""):
            result = self._execute()

        self.assertEqual(result.total_dispatches, 0)
        self.assertEqual(result.converted_payments, 0)
        self.assertEqual(result.recovered_revenue, Decimal("0"))

    def test_uses_cache_for_historical_date_ranges(self):
        historical_end = timezone.localdate() - timedelta(days=2)
        historical_start = historical_end - timedelta(days=7)
        broadcast = self._create_broadcast(status=BroadcastStatus.DELIVERED)
        BroadcastMessage.objects.filter(pk=broadcast.pk).update(
            created_at=datetime.combine(
                historical_end,
                datetime.min.time(),
                tzinfo=dt_timezone.utc,
            )
        )

        dto = GetPaymentRecoveryConversionMetricsDTO(
            project_uuid=self.project.uuid,
            start_date=historical_start,
            end_date=historical_end,
        )
        first_result = self.use_case.execute(dto)
        self.assertEqual(first_result.total_dispatches, 1)
        BroadcastMessage.objects.all().delete()
        second_result = self.use_case.execute(dto)

        self.assertEqual(first_result, second_result)
        cache_key = CACHE_KEY_TEMPLATE.format(
            project_uuid=self.project.uuid,
            agent_scope="all",
            start_date=historical_start.isoformat(),
            end_date=historical_end.isoformat(),
        )
        self.assertIsNotNone(cache.get(cache_key))

    def test_uses_short_cache_when_date_range_includes_today(self):
        self._create_broadcast(status=BroadcastStatus.DELIVERED)

        first_result = self._execute()
        BroadcastMessage.objects.all().delete()
        second_result = self._execute()

        self.assertEqual(first_result, second_result)
        cache_key = CACHE_KEY_TEMPLATE.format(
            project_uuid=self.project.uuid,
            agent_scope="all",
            start_date=self.start_date.isoformat(),
            end_date=self.end_date.isoformat(),
        )
        self.assertIsNotNone(cache.get(cache_key))

    @patch(
        "retail.broadcasts.usecases.get_payment_recovery_conversion_metrics.cache.set"
    )
    def test_uses_one_minute_ttl_for_current_day_ranges(self, mock_cache_set):
        self._create_broadcast(status=BroadcastStatus.DELIVERED)
        self._execute()

        mock_cache_set.assert_called_once()
        self.assertEqual(
            mock_cache_set.call_args.kwargs["timeout"], CURRENT_DAY_CACHE_TTL_SECONDS
        )

    @patch(
        "retail.broadcasts.usecases.get_payment_recovery_conversion_metrics.cache.set"
    )
    def test_uses_long_ttl_for_historical_ranges(self, mock_cache_set):
        historical_end = timezone.localdate() - timedelta(days=2)
        historical_start = historical_end - timedelta(days=7)
        dto = GetPaymentRecoveryConversionMetricsDTO(
            project_uuid=self.project.uuid,
            start_date=historical_start,
            end_date=historical_end,
        )
        self.use_case.execute(dto)

        mock_cache_set.assert_called_once()
        self.assertEqual(
            mock_cache_set.call_args.kwargs["timeout"], HISTORICAL_CACHE_TTL_SECONDS
        )

    def test_only_counts_conversions_linked_to_filtered_dispatches(self):
        in_range_broadcast = self._create_broadcast(status=BroadcastStatus.DELIVERED)
        self._create_broadcast(
            status=BroadcastStatus.DELIVERED, order_id="no-conversion"
        )

        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            broadcast=in_range_broadcast,
            order_id=in_range_broadcast.order_id,
            value=Decimal("50.00"),
        )
        BroadcastConversion.objects.create(
            project=self.project,
            integrated_agent=self.integrated_agent,
            order_id="orphan-order",
            value=Decimal("999.00"),
        )

        result = self._execute()

        self.assertEqual(result.total_dispatches, 2)
        self.assertEqual(result.converted_payments, 1)
        self.assertEqual(result.conversion_rate, Decimal("50.00"))
        self.assertEqual(result.recovered_revenue, Decimal("50.00"))
