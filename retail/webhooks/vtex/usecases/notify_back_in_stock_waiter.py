import logging
from typing import List, Optional
from uuid import UUID

from django.db.models import QuerySet
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
_UNSENT_STATUSES = (
    BackInStockWaiter.STATUS_PENDING,
    BackInStockWaiter.STATUS_ERROR,
)


class NotifyBackInStockWaiterUseCase:
    """Queue 2: send WhatsApp for one waiter, then mark sent and maybe SREM."""

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
    ) -> None:
        waiter = self._retryable_waiter(waiter_uuid)
        if waiter is None:
            logger.info(
                f"[BACK_IN_STOCK] Notify skipped: vtex_account={account} "
                f"sku_id={sku_id} waiter_uuid={waiter_uuid} reason=already_sent_or_missing"
            )
            return

        try:
            result = self._send_use_case.execute(
                ProcessBackInStockNotificationDTO(
                    sku_id=sku_id,
                    phone=phone,
                    name=name,
                    locale=locale,
                )
            )
        except Exception as exc:
            self._mark_error(waiter, ERROR_SEND_FAILED, str(exc))
            self._srem_if_sku_has_no_pending(account, waiter)
            raise

        if result.discarded:
            logger.info(
                f"[BACK_IN_STOCK] Notify skipped, waiter stays pending: "
                f"vtex_account={account} sku_id={sku_id} "
                f"waiter_uuid={waiter_uuid} reason={result.reason}"
            )
            return

        self._mark_sent(waiter)
        self._srem_if_sku_has_no_pending(account, waiter)
        logger.info(
            f"[BACK_IN_STOCK] Waiter marked sent: vtex_account={account} "
            f"sku_id={sku_id} waiter_uuid={waiter_uuid}"
        )

    def _retryable_waiter(self, waiter_uuid: str) -> Optional[BackInStockWaiter]:
        try:
            waiter = BackInStockWaiter.objects.get(uuid=UUID(waiter_uuid))
        except (BackInStockWaiter.DoesNotExist, ValueError):
            return None
        if waiter.status == BackInStockWaiter.STATUS_SENT:
            return None
        return waiter

    def _mark_sent(self, waiter: BackInStockWaiter) -> None:
        if not self._update_unsent_waiter(
            waiter,
            status=BackInStockWaiter.STATUS_SENT,
            sent_at=timezone.now(),
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
            error_details=reasons,
        ):
            return
        waiter.status = BackInStockWaiter.STATUS_ERROR
        waiter.error_details = reasons

    def _update_unsent_waiter(self, waiter: BackInStockWaiter, **fields) -> bool:
        """One-row CAS: pk is the row, status is the version.

        Two notify tasks can load the same pending waiter. The first to
        finish marks ``sent``; the second must not overwrite ``sent_at``
        or demote ``sent`` back to ``error``.
        """
        return bool(
            BackInStockWaiter.objects.filter(
                pk=waiter.pk,
                status__in=_UNSENT_STATUSES,
            ).update(**fields)
        )

    def _srem_if_sku_has_no_pending(
        self, account: str, waiter: BackInStockWaiter
    ) -> None:
        if self._pending_for_sku(waiter).exists():
            return
        self._index.srem_waiting_sku(account, waiter.sku_id)

    def _pending_for_sku(self, waiter: BackInStockWaiter) -> QuerySet:
        return BackInStockWaiter.objects.filter(
            project_id=waiter.project_id,
            sku_id=waiter.sku_id,
            status=BackInStockWaiter.STATUS_PENDING,
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
