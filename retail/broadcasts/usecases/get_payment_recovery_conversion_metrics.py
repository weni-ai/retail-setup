"""Use case: payment recovery conversion metrics for copy-pix automation."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone as dt_timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Optional
from uuid import UUID

from django.conf import settings
from django.core.cache import cache
from django.db.models import Count, DecimalField, Max, Min, Sum
from django.db.models.functions import Coalesce

from retail.broadcasts.models import BroadcastMessage, BroadcastStatus

CACHE_KEY_TEMPLATE = (
    "broadcasts:payment_recovery_metrics:{project_uuid}:{agent_scope}:"
    "{start_date}:{end_date}"
)
# Closed date ranges (end_date strictly before today UTC) are stable — cache longer.
HISTORICAL_CACHE_TTL_SECONDS = 3600
# Ranges that include today may still change; short TTL coalesces burst traffic.
CURRENT_DAY_CACHE_TTL_SECONDS = 60

_EXCLUDED_DISPATCH_STATUSES = (
    BroadcastStatus.QUEUED,
    BroadcastStatus.FAILED,
)
_TWO_DECIMAL_PLACES = Decimal("0.01")


@dataclass(frozen=True)
class GetPaymentRecoveryConversionMetricsDTO:
    """Input for ``GetPaymentRecoveryConversionMetricsUseCase``.

    Metrics are scoped to payment-recovery dispatches whose
    ``created_at`` falls within the inclusive UTC calendar range.
    When ``integrated_agent_uuid`` is set, results are further
    restricted to that integrated agent.
    """

    project_uuid: UUID
    start_date: date
    end_date: date
    integrated_agent_uuid: Optional[UUID] = None


@dataclass(frozen=True)
class PaymentRecoveryConversionMetricsResult:
    total_dispatches: int
    converted_payments: int
    conversion_rate: Decimal
    recovered_revenue: Decimal
    average_ticket: Optional[Decimal]
    first_conversion_at: Optional[datetime]
    last_conversion_at: Optional[datetime]


class GetPaymentRecoveryConversionMetricsUseCase:
    """Return payment-recovery conversion metrics aligned with PM analytics.

    Dispatch denominator: ``BroadcastMessage`` rows whose status is not
    ``queued`` or ``failed`` and whose ``created_at`` is in range.
    Conversion numerator: distinct ``BroadcastConversion`` rows linked to
    those dispatches via ``broadcast_id`` (last-touch attribution).
    """

    def execute(
        self, dto: GetPaymentRecoveryConversionMetricsDTO
    ) -> PaymentRecoveryConversionMetricsResult:
        cache_ttl = self._resolve_cache_ttl(dto.end_date)
        cache_key = self._build_cache_key(dto)
        cached = cache.get(cache_key)
        if cached is not None:
            return self._deserialize(cached)

        result = self._compute(dto)
        cache.set(cache_key, self._serialize(result), timeout=cache_ttl)
        return result

    def _compute(
        self, dto: GetPaymentRecoveryConversionMetricsDTO
    ) -> PaymentRecoveryConversionMetricsResult:
        payment_recovery_agent_uuid = getattr(
            settings, "PAYMENT_RECOVERY_AGENT_UUID", ""
        )
        if not payment_recovery_agent_uuid:
            return self._empty_result()

        start_dt = datetime.combine(dto.start_date, time.min, tzinfo=dt_timezone.utc)
        end_dt = datetime.combine(dto.end_date, time.max, tzinfo=dt_timezone.utc)

        queryset = BroadcastMessage.objects.filter(
            project__uuid=dto.project_uuid,
            integrated_agent__agent_id=payment_recovery_agent_uuid,
            created_at__range=(start_dt, end_dt),
        ).exclude(status__in=_EXCLUDED_DISPATCH_STATUSES)

        if dto.integrated_agent_uuid is not None:
            queryset = queryset.filter(integrated_agent__uuid=dto.integrated_agent_uuid)

        aggregates = queryset.aggregate(
            total_dispatches=Count("id", distinct=True),
            converted_payments=Count("conversions", distinct=True),
            recovered_revenue=Coalesce(
                Sum("conversions__value"),
                Decimal("0"),
                output_field=DecimalField(max_digits=14, decimal_places=2),
            ),
            first_conversion_at=Min("conversions__converted_at"),
            last_conversion_at=Max("conversions__converted_at"),
        )

        total_dispatches = aggregates["total_dispatches"] or 0
        converted_payments = aggregates["converted_payments"] or 0
        recovered_revenue = aggregates["recovered_revenue"] or Decimal("0")

        return PaymentRecoveryConversionMetricsResult(
            total_dispatches=total_dispatches,
            converted_payments=converted_payments,
            conversion_rate=self._calculate_conversion_rate(
                converted_payments, total_dispatches
            ),
            recovered_revenue=recovered_revenue,
            average_ticket=self._calculate_average_ticket(
                recovered_revenue, converted_payments
            ),
            first_conversion_at=aggregates["first_conversion_at"],
            last_conversion_at=aggregates["last_conversion_at"],
        )

    @staticmethod
    def _calculate_conversion_rate(
        converted_payments: int, total_dispatches: int
    ) -> Decimal:
        if total_dispatches == 0:
            return Decimal("0")
        rate = Decimal(converted_payments) / Decimal(total_dispatches) * Decimal("100")
        return rate.quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def _calculate_average_ticket(
        recovered_revenue: Decimal, converted_payments: int
    ) -> Optional[Decimal]:
        if converted_payments == 0:
            return None
        average = recovered_revenue / Decimal(converted_payments)
        return average.quantize(_TWO_DECIMAL_PLACES, rounding=ROUND_HALF_UP)

    @staticmethod
    def _empty_result() -> PaymentRecoveryConversionMetricsResult:
        return PaymentRecoveryConversionMetricsResult(
            total_dispatches=0,
            converted_payments=0,
            conversion_rate=Decimal("0"),
            recovered_revenue=Decimal("0"),
            average_ticket=None,
            first_conversion_at=None,
            last_conversion_at=None,
        )

    @staticmethod
    def _resolve_cache_ttl(end_date: date) -> int:
        """Return cache TTL based on whether the range includes today (UTC).

        Past-only ranges use a long TTL because metrics are stable.
        Ranges reaching today use a short TTL to limit staleness while
        still coalescing repeated dashboard refreshes.
        """
        today_utc = datetime.now(dt_timezone.utc).date()
        if end_date >= today_utc:
            return CURRENT_DAY_CACHE_TTL_SECONDS
        return HISTORICAL_CACHE_TTL_SECONDS

    @staticmethod
    def _build_cache_key(dto: GetPaymentRecoveryConversionMetricsDTO) -> str:
        agent_scope = (
            str(dto.integrated_agent_uuid)
            if dto.integrated_agent_uuid is not None
            else "all"
        )
        return CACHE_KEY_TEMPLATE.format(
            project_uuid=dto.project_uuid,
            agent_scope=agent_scope,
            start_date=dto.start_date.isoformat(),
            end_date=dto.end_date.isoformat(),
        )

    @staticmethod
    def _serialize(result: PaymentRecoveryConversionMetricsResult) -> dict[str, Any]:
        return {
            "total_dispatches": result.total_dispatches,
            "converted_payments": result.converted_payments,
            "conversion_rate": str(result.conversion_rate),
            "recovered_revenue": str(result.recovered_revenue),
            "average_ticket": (
                str(result.average_ticket)
                if result.average_ticket is not None
                else None
            ),
            "first_conversion_at": (
                result.first_conversion_at.isoformat()
                if result.first_conversion_at is not None
                else None
            ),
            "last_conversion_at": (
                result.last_conversion_at.isoformat()
                if result.last_conversion_at is not None
                else None
            ),
        }

    @staticmethod
    def _deserialize(payload: dict[str, Any]) -> PaymentRecoveryConversionMetricsResult:
        first_conversion_at = payload.get("first_conversion_at")
        last_conversion_at = payload.get("last_conversion_at")
        average_ticket = payload.get("average_ticket")

        return PaymentRecoveryConversionMetricsResult(
            total_dispatches=payload["total_dispatches"],
            converted_payments=payload["converted_payments"],
            conversion_rate=Decimal(payload["conversion_rate"]),
            recovered_revenue=Decimal(payload["recovered_revenue"]),
            average_ticket=(
                Decimal(average_ticket) if average_ticket is not None else None
            ),
            first_conversion_at=(
                datetime.fromisoformat(first_conversion_at)
                if first_conversion_at is not None
                else None
            ),
            last_conversion_at=(
                datetime.fromisoformat(last_conversion_at)
                if last_conversion_at is not None
                else None
            ),
        )
