import logging
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.conf import settings

from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.agents.shared.cache import AgentRole
from retail.clients.exceptions import CustomAPIException
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.models import BackInStockWaiter
from retail.vtex.waiting_skus import WaitingSkusIndex
from retail.webhooks.vtex.usecases.exceptions import BackInStockStockCheckError


logger = logging.getLogger(__name__)

NOTIFY_AVAILABILITIES = frozenset({"available", "cannotBeDelivered"})


class ProcessBackInStockStockChangeUseCase:
    """Queue 1: Logistics + Checkout per offer, then one notify task per shopper."""

    def __init__(
        self,
        vtex_io_service: Optional[VtexIOService] = None,
        index: Optional[WaitingSkusIndex] = None,
        notify_task: Optional[Any] = None,
        agent_lookup: Optional[BaseAgentWebhookUseCase] = None,
    ) -> None:
        self._vtex_io = vtex_io_service or VtexIOService()
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

        if self._inventory_total(account, sku_id) == 0:
            logger.info(
                f"[BACK_IN_STOCK] Inventory empty: vtex_account={account} "
                f"sku_id={sku_id}"
            )
            return

        grouped = _group_waiters_by_offer(waiters)
        availability_by_offer: Dict[Tuple[str, str], str] = {}
        queued = 0
        for (seller, sales_channel), offer_waiters in grouped.items():
            offer = (seller, sales_channel)
            if offer not in availability_by_offer:
                availability_by_offer[offer] = self._simulate_offer(
                    account, sku_id, seller, sales_channel
                )
            if availability_by_offer[offer] not in NOTIFY_AVAILABILITIES:
                continue
            for waiter in offer_waiters:
                self._enqueue_notify(account, waiter)
                queued += 1

        logger.info(
            f"[BACK_IN_STOCK] Stock-change job finished: vtex_account={account} "
            f"sku_id={sku_id} pending={len(waiters)} queued={queued}"
        )

    def _has_active_back_in_stock_agent(self, project: Project) -> bool:
        return (
            self._agent_lookup.get_integrated_agent_if_exists(
                project, AgentRole.BACK_IN_STOCK
            )
            is not None
        )

    def _inventory_total(self, account: str, sku_id: str) -> int:
        payload = self._proxy(
            account,
            method="GET",
            path=f"/api/logistics/pvt/inventory/skus/{sku_id}",
        )
        return _sum_inventory(payload)

    def _simulate_offer(
        self, account: str, sku_id: str, seller: str, sales_channel: str
    ) -> str:
        payload = self._proxy(
            account,
            method="POST",
            path="/api/checkout/pub/orderForms/simulation",
            params={"sc": sales_channel},
            data={
                "items": [{"id": sku_id, "quantity": 1, "seller": seller}],
            },
        )
        return _item_availability(payload)

    def _proxy(
        self,
        account: str,
        method: str,
        path: str,
        params: Optional[dict] = None,
        data: Optional[dict] = None,
    ) -> dict:
        try:
            return self._vtex_io.proxy_vtex(
                account_domain=f"{account}.myvtex.com",
                vtex_account=account,
                method=method,
                path=path,
                params=params,
                data=data,
            )
        except CustomAPIException as exc:
            logger.error(
                f"[BACK_IN_STOCK] VTEX stock check failed: vtex_account={account} "
                f"path={path} status={exc.status_code}"
            )
            raise BackInStockStockCheckError(
                "VTEX logistics or checkout check failed."
            ) from exc

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
            },
            queue=settings.BACK_IN_STOCK_NOTIFY_CELERY_QUEUE,
        )


def _notify_task():
    from retail.vtex.tasks import task_notify_back_in_stock_waiter

    return task_notify_back_in_stock_waiter


def _group_waiters_by_offer(
    waiters: Iterable[BackInStockWaiter],
) -> Dict[Tuple[str, str], List[BackInStockWaiter]]:
    grouped: Dict[Tuple[str, str], List[BackInStockWaiter]] = defaultdict(list)
    for waiter in waiters:
        grouped[(waiter.seller, waiter.sales_channel)].append(waiter)
    return grouped


def _sum_inventory(payload: Any) -> int:
    if not isinstance(payload, dict):
        return 0
    total = 0
    for row in payload.get("balance") or []:
        if not isinstance(row, dict):
            continue
        if row.get("hasUnlimitedQuantity"):
            return 1
        quantity = row.get("availableQuantity")
        if quantity is None:
            quantity = row.get("totalQuantity", 0)
        total += int(quantity or 0)
    return total


def _item_availability(payload: Any) -> str:
    if not isinstance(payload, dict):
        return "withoutStock"
    items = payload.get("items") or []
    if not items or not isinstance(items[0], dict):
        return "withoutStock"
    return items[0].get("availability") or "withoutStock"
