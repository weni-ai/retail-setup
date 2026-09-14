import logging
from datetime import datetime, timedelta

from django.utils import timezone

from retail.vtex.models import BackInStockWaiter


logger = logging.getLogger(__name__)

SENT_WAITER_RETENTION_DAYS = 30
CLEANUP_BATCH_SIZE = 5000


class CleanupBackInStockSubscriptionsUseCase:
    """Purge ``sent`` waiters after 30 days, in bounded DELETE batches.

    ``pending``, in-flight, and ``error`` stay until a WhatsApp send
    succeeds (or the shopper subscribes again). Avise-me rows are
    never dropped just because they are old.

    Django cannot ``DELETE`` a sliced queryset, so each batch selects
    PKs then deletes ``pk__in``. That keeps statements short-lived;
    if a batch fails, already-deleted rows stay committed and the
    next beat run continues.
    """

    def execute(self) -> None:
        threshold = timezone.now() - timedelta(days=SENT_WAITER_RETENTION_DAYS)
        deleted = self._delete_stale_sent_waiters(threshold)
        logger.info(
            f"[BACK_IN_STOCK] Sent waiter cleanup finished: "
            f"deleted={deleted} older_than_days={SENT_WAITER_RETENTION_DAYS}"
        )

    def _delete_stale_sent_waiters(self, threshold: datetime) -> int:
        stale = BackInStockWaiter.objects.filter(
            status=BackInStockWaiter.STATUS_SENT,
            sent_at__lt=threshold,
        ).order_by("pk")
        total_deleted = 0
        while True:
            batch_ids = list(stale.values_list("pk", flat=True)[:CLEANUP_BATCH_SIZE])
            if not batch_ids:
                break
            deleted, _ = BackInStockWaiter.objects.filter(pk__in=batch_ids).delete()
            total_deleted += deleted
        return total_deleted
