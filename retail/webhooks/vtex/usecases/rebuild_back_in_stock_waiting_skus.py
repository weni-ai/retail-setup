import logging
from typing import Optional

from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.vtex.models import BackInStockWaiter
from retail.vtex.waiting_skus import WaitingSkusIndex


logger = logging.getLogger(__name__)


class RebuildBackInStockWaitingSkusUseCase:
    """Rebuild each store SET from pending waiters (database is the source of truth)."""

    def __init__(
        self,
        index: Optional[WaitingSkusIndex] = None,
        project_lookup: Optional[BaseAgentWebhookUseCase] = None,
    ) -> None:
        self._index = index or WaitingSkusIndex()
        self._project_lookup = project_lookup or BaseAgentWebhookUseCase()

    def execute(self) -> None:
        project_rows = (
            BackInStockWaiter.objects.filter(status=BackInStockWaiter.STATUS_PENDING)
            .exclude(project__vtex_account__isnull=True)
            .exclude(project__vtex_account="")
            .values_list("project_id", "project__vtex_account")
            .distinct()
        )
        rebuilt = 0
        for project_id, vtex_account in project_rows:
            self.execute_for_project(project_id, vtex_account)
            rebuilt += 1
        logger.info(f"[BACK_IN_STOCK] Waiting SKU index rebuilt: accounts={rebuilt}")

    def execute_for_account(self, account: str) -> None:
        project = self._project_lookup.get_project_by_vtex_account(account)
        if project is None:
            logger.info(
                f"[BACK_IN_STOCK] Rebuild skipped: vtex_account={account} "
                f"reason=project_not_found"
            )
            self._index.rebuild_for_account(account, [])
            return
        self.execute_for_project(project.id, account)

    def execute_for_project(self, project_id: int, account: str) -> None:
        sku_ids = list(
            BackInStockWaiter.objects.filter(
                project_id=project_id,
                status=BackInStockWaiter.STATUS_PENDING,
            )
            .values_list("sku_id", flat=True)
            .distinct()
        )
        self._index.rebuild_for_account(account, sku_ids)
        logger.info(
            f"[BACK_IN_STOCK] Waiting SKU index rebuilt: vtex_account={account} "
            f"skus={len(sku_ids)}"
        )
