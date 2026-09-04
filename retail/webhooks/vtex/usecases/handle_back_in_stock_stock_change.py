import logging
from typing import Any, Optional

from django.conf import settings

from retail.vtex.waiting_skus import WaitingSkusIndex
from retail.webhooks.vtex.usecases.dto import (
    BackInStockStockChangeDTO,
    BackInStockStockChangeResult,
)
from retail.webhooks.vtex.usecases.rebuild_back_in_stock_waiting_skus import (
    RebuildBackInStockWaitingSkusUseCase,
)


logger = logging.getLogger(__name__)

SKU_NOT_WAITING = "sku_not_waiting"


class HandleBackInStockStockChangeUseCase:
    """Accept a stock-change only when the SKU is in the waiting SET."""

    def __init__(
        self,
        index: Optional[WaitingSkusIndex] = None,
        rebuild_use_case: Optional[RebuildBackInStockWaitingSkusUseCase] = None,
        stock_change_task: Optional[Any] = None,
    ) -> None:
        self._index = index or WaitingSkusIndex()
        self._rebuild_use_case = (
            rebuild_use_case or RebuildBackInStockWaitingSkusUseCase(index=self._index)
        )
        self._stock_change_task = stock_change_task

    def execute(self, dto: BackInStockStockChangeDTO) -> BackInStockStockChangeResult:
        is_waiting = self._index.sku_is_waiting(
            dto.account,
            dto.sku_id,
            on_missing_key=lambda: self._rebuild_use_case.execute_for_account(
                dto.account
            ),
        )
        if not is_waiting:
            logger.info(
                f"[BACK_IN_STOCK] Stock change skipped: vtex_account={dto.account} "
                f"sku_id={dto.sku_id} reason={SKU_NOT_WAITING}"
            )
            return BackInStockStockChangeResult(accepted=False, reason=SKU_NOT_WAITING)

        self._enqueue_stock_change(dto)
        logger.info(
            f"[BACK_IN_STOCK] Stock change accepted: vtex_account={dto.account} "
            f"sku_id={dto.sku_id}"
        )
        return BackInStockStockChangeResult(accepted=True)

    def _enqueue_stock_change(self, dto: BackInStockStockChangeDTO) -> None:
        task = self._stock_change_task or _stock_change_task()
        task.apply_async(
            kwargs={"account": dto.account, "sku_id": dto.sku_id},
            queue=settings.BACK_IN_STOCK_STOCK_CHANGE_CELERY_QUEUE,
        )


def _stock_change_task():
    from retail.vtex.tasks import task_process_back_in_stock_stock_change

    return task_process_back_in_stock_stock_change
