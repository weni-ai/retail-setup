import logging

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from django.core.cache import cache
from django.db.models import Q

from retail.broadcasts.models import (
    BroadcastConversion,
    BroadcastMessage,
    BroadcastStatus,
)
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)


# Statuses that disqualify a broadcast from being credited as the
# attribution source of a conversion. ERRORED/FAILED never reached the
# recipient, and UNKNOWN means we could not interpret what happened on
# the courier side, so attributing a sale to it would be misleading.
_BROADCAST_STATUSES_INELIGIBLE_FOR_CONVERSION = (
    BroadcastStatus.ERRORED,
    BroadcastStatus.FAILED,
    BroadcastStatus.UNKNOWN,
)


@dataclass(frozen=True)
class _OrderConversionDetails:
    """Subset of VTEX order data relevant for conversion attribution.

    Empty / ``None`` fields signal "VTEX lookup did not return that
    information" and translate to leaving the corresponding column on
    the ``BroadcastConversion`` row NULL or empty.
    """

    order_form_id: Optional[str]
    value: Optional[Decimal]
    currency: str


class MarkBroadcastConvertedUseCase:
    """Records a BroadcastConversion when an order tied to a broadcast is invoiced.

    The trigger is the VTEX ``invoiced`` event arriving on
    ``task_order_status_update``. The use case follows three steps:

    1. Pull the canonical ``order_form_id`` / ``value`` / ``currency``
       from VTEX so the conversion row is filled with authoritative
       data even if the originating broadcast only knew one identifier.
    2. Pick the last-touch broadcast (most recent non-failed dispatch
       that matches by ``order_id`` or ``order_form_id``) so the
       conversion can be attributed to a specific ``integrated_agent``.
       No broadcast match means an organic purchase and is a no-op —
       the conversion table tracks broadcast-driven sales only.
    3. Create a single ``BroadcastConversion`` row per (project,
       order_id). Idempotency is enforced by the unique constraint at
       the database level: a duplicate insert raises ``IntegrityError``
       and is logged as a warning, never propagated.
    """

    def __init__(self, vtex_io_service: Optional[VtexIOService] = None):
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def execute(self, order_id: str, project_uuid: str) -> None:
        if not order_id:
            logger.info(
                f"[CONVERSION_TRACKING] conversion_skip_missing_order_id: "
                f"project_uuid={project_uuid}"
            )
            return

        project = self._get_project(project_uuid)
        if project is None:
            return

        details = self._fetch_conversion_details(order_id, project)

        last_touch_broadcast = self._select_last_touch_broadcast(
            project=project,
            order_id=order_id,
            order_form_id=details.order_form_id,
        )
        if last_touch_broadcast is None:
            logger.info(
                f"[CONVERSION_TRACKING] no_broadcast_for_invoiced_order: "
                f"project_uuid={project.uuid} order_id={order_id} "
                f"order_form_id={details.order_form_id}"
            )
            return

        self._create_conversion(
            project=project,
            order_id=order_id,
            details=details,
            last_touch_broadcast=last_touch_broadcast,
        )

    @staticmethod
    def _get_project(project_uuid: str) -> Optional[Project]:
        """Resolve a Project by UUID, sharing the project_by_uuid cache.

        Uses the same cache key (``project_by_uuid_<uuid>``) and TTL as
        ``HandlePurchaseEventUseCase._get_project`` so a single Redis
        entry serves both the CAPI flow and the conversion flow.
        ``Project.clear_cache`` already invalidates this key on save.
        """
        cache_key = f"project_by_uuid_{project_uuid}"
        cached_project = cache.get(cache_key)
        if cached_project is not None:
            return cached_project

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            logger.info(
                f"[CONVERSION_TRACKING] conversion_skip_project_not_found: "
                f"project_uuid={project_uuid}"
            )
            return None
        except Project.MultipleObjectsReturned:
            logger.error(
                f"[CONVERSION_TRACKING] conversion_skip_multiple_projects: "
                f"project_uuid={project_uuid}",
                exc_info=True,
            )
            return None

        cache.set(cache_key, project, timeout=43200)
        return project

    def _fetch_conversion_details(
        self, order_id: str, project: Project
    ) -> _OrderConversionDetails:
        """Pull conversion-relevant fields from the VTEX order details.

        Wraps the upstream call in a broad ``except`` so a transient
        VTEX I/O failure becomes a no-op detail (and only the
        ``order_id`` lookup branch will be considered) instead of
        propagating up and aborting the whole task.
        """
        account_domain = f"{project.vtex_account}.myvtex.com"
        try:
            order_details = self.vtex_io_service.get_order_details_by_id(
                account_domain=account_domain,
                vtex_account=project.vtex_account,
                order_id=order_id,
            )
        except Exception as exc:
            logger.warning(
                f"[CONVERSION_TRACKING] conversion_vtex_lookup_failed: "
                f"project_uuid={project.uuid} order_id={order_id} error={exc}"
            )
            return _OrderConversionDetails(
                order_form_id=None,
                value=None,
                currency="",
            )

        if not order_details:
            return _OrderConversionDetails(
                order_form_id=None,
                value=None,
                currency="",
            )

        order_form_id = order_details.get("orderFormId")
        store_preferences = order_details.get("storePreferencesData") or {}
        currency = store_preferences.get("currencyCode") or ""

        return _OrderConversionDetails(
            order_form_id=str(order_form_id) if order_form_id else None,
            value=self._extract_value(order_details),
            currency=currency,
        )

    @staticmethod
    def _extract_value(order_details: dict) -> Optional[Decimal]:
        """Convert VTEX order value (cents) to a Decimal in major units.

        VTEX returns ``order.value`` in minor units (cents). Returning
        ``None`` for missing/invalid values keeps the column NULL so
        absent data does not skew aggregate revenue metrics.
        """
        raw_value = order_details.get("value")
        if raw_value in (None, ""):
            return None
        try:
            return (Decimal(raw_value) / Decimal(100)).quantize(Decimal("0.01"))
        except (TypeError, ValueError, ArithmeticError):
            return None

    @staticmethod
    def _select_last_touch_broadcast(
        project: Project,
        order_id: str,
        order_form_id: Optional[str],
    ) -> Optional[BroadcastMessage]:
        """Pick the most recent eligible broadcast this conversion can be attributed to.

        ``select_related("integrated_agent")`` avoids an extra query
        when the caller dereferences the agent for attribution.
        """
        match_filter = Q(order_id=order_id)
        if order_form_id:
            match_filter |= Q(order_form_id=order_form_id)

        return (
            BroadcastMessage.objects.select_related("integrated_agent")
            .filter(project=project)
            .filter(match_filter)
            .exclude(status__in=_BROADCAST_STATUSES_INELIGIBLE_FOR_CONVERSION)
            .order_by("-created_at")
            .first()
        )

    @staticmethod
    def _create_conversion(
        project: Project,
        order_id: str,
        details: _OrderConversionDetails,
        last_touch_broadcast: BroadcastMessage,
    ) -> None:
        """Persist a BroadcastConversion or log a warning if it already exists.

        ``get_or_create`` wraps the SELECT + INSERT in its own
        ``transaction.atomic`` and recovers from concurrent
        ``IntegrityError`` on the ``(project, order_id)`` unique
        constraint, which gives us idempotency for free without
        having to handle the race manually.
        """
        order_form_id = last_touch_broadcast.order_form_id or details.order_form_id

        conversion, created = BroadcastConversion.objects.get_or_create(
            project=project,
            order_id=order_id,
            defaults={
                "integrated_agent": last_touch_broadcast.integrated_agent,
                "order_form_id": order_form_id,
                "value": details.value,
                "currency": details.currency,
            },
        )

        if not created:
            logger.warning(
                f"[CONVERSION_TRACKING] conversion_already_recorded: "
                f"project_uuid={project.uuid} order_id={order_id} "
                f"existing_conversion_uuid={conversion.uuid} "
                f"existing_converted_at={conversion.converted_at.isoformat()}"
            )
            return

        logger.info(
            f"[CONVERSION_TRACKING] converted: "
            f"conversion_uuid={conversion.uuid} "
            f"project_uuid={project.uuid} "
            f"agent_uuid={conversion.integrated_agent_id} "
            f"order_id={conversion.order_id} "
            f"order_form_id={conversion.order_form_id} "
            f"value={conversion.value} currency={conversion.currency} "
            f"last_touch_broadcast_uuid={last_touch_broadcast.uuid}"
        )
