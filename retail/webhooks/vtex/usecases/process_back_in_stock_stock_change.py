import logging
from typing import Any, Optional

from django.conf import settings

from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.agents.shared.cache import AgentRole
from retail.projects.models import Project
from retail.vtex.models import BackInStockWaiter
from retail.vtex.waiting_skus import WaitingSkusIndex


logger = logging.getLogger(__name__)


class ProcessBackInStockStockChangeUseCase:
    """Queue 1: fan out one notify task per pending waiter of the SKU.

    Availability (inventory, seller and trade policy) is resolved by the
    agent lambda at notify time, so this job only decides *who* is waiting
    and lets the lambda decide *whether* to send. It performs no VTEX
    availability calls.
    """

    def __init__(
        self,
        index: Optional[WaitingSkusIndex] = None,
        notify_task: Optional[Any] = None,
        agent_lookup: Optional[BaseAgentWebhookUseCase] = None,
    ) -> None:
        self._index = index or WaitingSkusIndex()
        self._notify_task = notify_task
        self._agent_lookup = agent_lookup or BaseAgentWebhookUseCase()

    def execute(self, account: str, sku_id: str) -> None:
        project = self._agent_lookup.get_project_by_vtex_account(account)
        if project is None:
            logger.info(
                f"[BACK_IN_STOCK] Stock-change job skipped: vtex_account={account} "
                f"sku_id={sku_id} reason=project_not_found"
            )
            return

        waiters = list(
            BackInStockWaiter.objects.filter(
                project=project,
                sku_id=sku_id,
                status=BackInStockWaiter.STATUS_PENDING,
            ).order_by("created_at")
        )
        if not waiters:
            self._index.srem_waiting_sku(account, sku_id)
            logger.info(
                f"[BACK_IN_STOCK] Stale waiting SKU removed: vtex_account={account} "
                f"sku_id={sku_id}"
            )
            return

        if not self._has_active_back_in_stock_agent(project):
            logger.info(
                f"[BACK_IN_STOCK] Stock-change job skipped: vtex_account={account} "
                f"sku_id={sku_id} reason=agent_inactive"
            )
            return

        for waiter in waiters:
            self._enqueue_notify(account, waiter)

        logger.info(
            f"[BACK_IN_STOCK] Stock-change job finished: vtex_account={account} "
            f"sku_id={sku_id} queued={len(waiters)}"
        )

    def _has_active_back_in_stock_agent(self, project: Project) -> bool:
        return (
            self._agent_lookup.get_integrated_agent_if_exists(
                project, AgentRole.BACK_IN_STOCK
            )
            is not None
        )

    def _enqueue_notify(self, account: str, waiter: BackInStockWaiter) -> None:
        task = self._notify_task or _notify_task()
        task.apply_async(
            kwargs={
                "account": account,
                "waiter_uuid": str(waiter.uuid),
                "sku_id": waiter.sku_id,
                "phone": waiter.phone,
                "name": waiter.name,
                "locale": waiter.locale,
                "seller": waiter.seller,
                "sales_channel": waiter.sales_channel,
            },
            queue=settings.BACK_IN_STOCK_NOTIFY_CELERY_QUEUE,
        )


def _notify_task():
    from retail.vtex.tasks import task_notify_back_in_stock_waiter

    return task_notify_back_in_stock_waiter
