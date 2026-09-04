import logging
from typing import Optional

from django.db import IntegrityError, transaction

from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.projects.models import Project
from retail.vtex.models import BackInStockWaiter
from retail.vtex.waiting_skus import WaitingSkusIndex
from retail.webhooks.vtex.usecases.dto import SubscribeBackInStockDTO
from retail.webhooks.vtex.usecases.exceptions import ProjectNotFoundError


logger = logging.getLogger(__name__)


class SubscribeBackInStockUseCase:
    """Persist a waiter and add the SKU to the Redis SET before HTTP 200."""

    def __init__(
        self,
        index: Optional[WaitingSkusIndex] = None,
        project_lookup: Optional[BaseAgentWebhookUseCase] = None,
    ) -> None:
        self._index = index or WaitingSkusIndex()
        self._project_lookup = project_lookup or BaseAgentWebhookUseCase()

    def execute(self, dto: SubscribeBackInStockDTO) -> None:
        project = self._get_project(dto.account)
        waiter = self._upsert_waiter(project, dto)
        self._index.sadd_waiting_sku(dto.account, dto.sku_id)
        logger.info(
            f"[BACK_IN_STOCK] Subscribe accepted: vtex_account={dto.account} "
            f"sku_id={dto.sku_id} waiter_uuid={waiter.uuid} status={waiter.status}"
        )

    def _get_project(self, account: str) -> Project:
        project = self._project_lookup.get_project_by_vtex_account(account)
        if project is None:
            raise ProjectNotFoundError()
        return project

    def _upsert_waiter(
        self, project: Project, dto: SubscribeBackInStockDTO
    ) -> BackInStockWaiter:
        defaults = {
            "name": dto.name,
            "locale": dto.locale or "pt-BR",
            "status": BackInStockWaiter.STATUS_PENDING,
            "sent_at": None,
        }
        lookup = {
            "project": project,
            "sku_id": dto.sku_id,
            "phone": dto.phone,
            "seller": dto.seller,
            "sales_channel": dto.sales_channel,
        }
        try:
            with transaction.atomic():
                waiter, created = BackInStockWaiter.objects.get_or_create(
                    **lookup, defaults=defaults
                )
        except IntegrityError:
            waiter = BackInStockWaiter.objects.get(**lookup)
            created = False

        if created:
            return waiter

        if waiter.status in (
            BackInStockWaiter.STATUS_SENT,
            BackInStockWaiter.STATUS_ERROR,
        ):
            waiter.status = BackInStockWaiter.STATUS_PENDING
            waiter.name = dto.name
            waiter.locale = dto.locale or waiter.locale
            waiter.sent_at = None
            waiter.error_details = []
            waiter.save(
                update_fields=["status", "name", "locale", "sent_at", "error_details"]
            )
        return waiter
