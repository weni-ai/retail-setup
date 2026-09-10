import logging
from typing import List, Optional
from uuid import UUID

from django.db.models import Q, QuerySet
from django.utils import timezone

from retail.vtex.models import BackInStockWaiter
from retail.vtex.waiting_skus import WaitingSkusIndex
from retail.webhooks.vtex.usecases.dto import (
    ProcessBackInStockNotificationDTO,
)
from retail.webhooks.vtex.usecases.process_back_in_stock_notification import (
    ProcessBackInStockNotificationUseCase,
)


logger = logging.getLogger(__name__)

ERROR_SEND_FAILED = "send_failed"
_CLAIMABLE_FOR_NOTIFY = (
    BackInStockWaiter.STATUS_PENDING,
    BackInStockWaiter.STATUS_ERROR,
    BackInStockWaiter.STATUS_SENDING,
)
_UNSENT_STATUSES = (
    BackInStockWaiter.STATUS_PENDING,
    BackInStockWaiter.STATUS_ERROR,
    BackInStockWaiter.STATUS_SENDING,
    BackInStockWaiter.STATUS_NOTIFYING,
)


class NotifyBackInStockWaiterUseCase:
    """Queue 2: claim the waiter, send WhatsApp, then mark sent and maybe SREM."""

    def __init__(
        self,
        send_use_case: ProcessBackInStockNotificationUseCase,
        index: Optional[WaitingSkusIndex] = None,
    ) -> None:
        self._send_use_case = send_use_case
        self._index = index or WaitingSkusIndex()

    def execute(
        self,
        account: str,
        waiter_uuid: str,
        sku_id: str,
        phone: str,
        name: str,
        locale: str,
        seller: str,
        sales_channel: str,
    ) -> None:
        waiter = self._claim_for_send(waiter_uuid)
        if waiter is None:
            logger.info(
                f"[BACK_IN_STOCK] Notify skipped: vtex_account={account} "
                f"sku_id={sku_id} waiter_uuid={waiter_uuid} reason=already_claimed_or_sent"
            )
            return

        try:
            result = self._send_use_case.execute(
                ProcessBackInStockNotificationDTO(
                    sku_id=sku_id,
                    phone=phone,
                    name=name,
                    locale=locale,
                    seller=seller,
                    sales_channel=sales_channel,
                )
            )
        except Exception as exc:
            self._mark_error(waiter, ERROR_SEND_FAILED, str(exc))
            self._srem_if_sku_has_no_indexed_waiters(account, waiter)
            raise

        if result.discarded:
            self._release_to_pending(waiter)
            logger.info(
                f"[BACK_IN_STOCK] Notify skipped, waiter stays pending: "
                f"vtex_account={account} sku_id={sku_id} "
                f"waiter_uuid={waiter_uuid} reason={result.reason}"
            )
            return

        self._mark_sent(waiter)
        self._srem_if_sku_has_no_indexed_waiters(account, waiter)
        logger.info(
            f"[BACK_IN_STOCK] Waiter marked sent: vtex_account={account} "
            f"sku_id={sku_id} waiter_uuid={waiter_uuid}"
        )

    def _claim_for_send(self, waiter_uuid: str) -> Optional[BackInStockWaiter]:
        try:
            waiter = BackInStockWaiter.objects.get(uuid=UUID(waiter_uuid))
        except (BackInStockWaiter.DoesNotExist, ValueError):
            return None
        if waiter.status == BackInStockWaiter.STATUS_SENT:
            return None

        now = timezone.now()
        stale_before = now - BackInStockWaiter.CLAIM_STALE_AFTER
        claimed = (
            BackInStockWaiter.objects.filter(pk=waiter.pk)
            .filter(
                Q(status__in=_CLAIMABLE_FOR_NOTIFY)
                | Q(
                    status=BackInStockWaiter.STATUS_NOTIFYING,
                    updated_at__lt=stale_before,
                )
            )
            .update(
                status=BackInStockWaiter.STATUS_NOTIFYING,
                updated_at=now,
            )
        )
        if not claimed:
            return None
        waiter.status = BackInStockWaiter.STATUS_NOTIFYING
        return waiter

    def _release_to_pending(self, waiter: BackInStockWaiter) -> None:
        if not self._update_unsent_waiter(
            waiter,
            status=BackInStockWaiter.STATUS_PENDING,
            updated_at=timezone.now(),
        ):
            return
        waiter.status = BackInStockWaiter.STATUS_PENDING

    def _mark_sent(self, waiter: BackInStockWaiter) -> None:
        if not self._update_unsent_waiter(
            waiter,
            status=BackInStockWaiter.STATUS_SENT,
            sent_at=timezone.now(),
            updated_at=timezone.now(),
            error_details=[],
        ):
            return
        waiter.status = BackInStockWaiter.STATUS_SENT
        waiter.error_details = []

    def _mark_error(self, waiter: BackInStockWaiter, code: str, message: str) -> None:
        reasons = _append_error_reason(waiter.error_details, code, message)
        if not self._update_unsent_waiter(
            waiter,
            status=BackInStockWaiter.STATUS_ERROR,
            updated_at=timezone.now(),
            error_details=reasons,
        ):
            return
        waiter.status = BackInStockWaiter.STATUS_ERROR
        waiter.error_details = reasons

    def _update_unsent_waiter(self, waiter: BackInStockWaiter, **fields) -> bool:
        """One-row CAS: pk is the row, status is the version.

        Two notify tasks can load the same waiter. The first to finish
        marks ``sent``; the second must not overwrite ``sent_at`` or
        demote ``sent`` back to ``error``.
        """
        return bool(
            BackInStockWaiter.objects.filter(
                pk=waiter.pk,
                status__in=_UNSENT_STATUSES,
            ).update(**fields)
        )

    def _srem_if_sku_has_no_indexed_waiters(
        self, account: str, waiter: BackInStockWaiter
    ) -> None:
        if self._indexed_for_sku(waiter).exists():
            return
        self._index.srem_waiting_sku(account, waiter.sku_id)

    def _indexed_for_sku(self, waiter: BackInStockWaiter) -> QuerySet:
        return BackInStockWaiter.objects.filter(
            project_id=waiter.project_id,
            sku_id=waiter.sku_id,
            status__in=BackInStockWaiter.INDEXED_STATUSES,
        )


def _append_error_reason(existing: Optional[List], code: str, message: str) -> list:
    reasons = list(existing or [])
    reasons.append(
        {
            "code": code,
            "message": message,
            "at": timezone.now().isoformat(),
        }
    )
    return reasons
