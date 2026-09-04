import logging
from datetime import timedelta

from django.utils import timezone

from retail.vtex.models import BackInStockWaiter


logger = logging.getLogger(__name__)

SENT_WAITER_RETENTION_DAYS = 30


class CleanupBackInStockSubscriptionsUseCase:
    """Purge ``sent`` waiters after 30 days.

    ``pending`` and ``error`` stay until a WhatsApp send succeeds (or
    the shopper subscribes again). Avise-me rows are never dropped
    just because they are old.
    """

    def execute(self) -> None:
        threshold = timezone.now() - timedelta(days=SENT_WAITER_RETENTION_DAYS)
        deleted, _ = BackInStockWaiter.objects.filter(
            status=BackInStockWaiter.STATUS_SENT,
            sent_at__lt=threshold,
        ).delete()
        logger.info(
            f"[BACK_IN_STOCK] Sent waiter cleanup finished: "
            f"deleted={deleted} older_than_days={SENT_WAITER_RETENTION_DAYS}"
        )
