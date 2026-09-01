import logging
from typing import Any, Optional

from django.conf import settings

from retail.vtex.tasks import task_process_back_in_stock_notification
from retail.webhooks.vtex.usecases.dto import EnqueueBackInStockNotificationsDTO


logger = logging.getLogger(__name__)


class EnqueueBackInStockNotificationsUseCase:
    """Queue one send task per shopper, preserving IO array order (FIFO)."""

    def __init__(self, process_task: Optional[Any] = None) -> None:
        self._process_task = process_task or task_process_back_in_stock_notification

    def execute(self, dto: EnqueueBackInStockNotificationsDTO) -> None:
        queue = settings.BACK_IN_STOCK_CELERY_QUEUE
        shopper_count = len(dto.shoppers)
        sku_id = dto.shoppers[0].sku_id
        logger.info(
            f"[BACK_IN_STOCK] Enqueueing batch: vtex_account={dto.account} "
            f"sku_id={sku_id} shoppers={shopper_count} queue={queue}"
        )
        for index, shopper in enumerate(dto.shoppers):
            try:
                self._process_task.apply_async(
                    kwargs={
                        "account": dto.account,
                        "sku_id": shopper.sku_id,
                        "phone": shopper.phone,
                        "name": shopper.name,
                        "locale": shopper.locale,
                    },
                    queue=queue,
                )
            except Exception:
                logger.error(
                    f"[BACK_IN_STOCK] Enqueue failed: vtex_account={dto.account} "
                    f"sku_id={shopper.sku_id} queued={index} "
                    f"remaining={shopper_count - index}"
                )
                raise
