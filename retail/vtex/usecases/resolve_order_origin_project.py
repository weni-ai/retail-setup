"""Route an order webhook from the ingress project to the origin project."""

import logging
from typing import Callable, Optional

from retail.projects.models import Project
from retail.vtex.sub_accounts import project_has_multiple_vtex_accounts
from retail.vtex.usecases.resolve_order_origin_account import (
    ResolveOrderOriginAccountUseCase,
)
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

logger = logging.getLogger(__name__)

ProjectLookup = Callable[[str], Optional[Project]]


class ResolveOrderOriginProjectUseCase:
    """Pick the project that should process an order webhook.

    When the ingress project has a single VTEX account, it is returned
    unchanged (no extra OMS call).
    """

    def __init__(
        self,
        origin_account_resolver: Optional[ResolveOrderOriginAccountUseCase] = None,
    ):
        self.origin_account_resolver = (
            origin_account_resolver or ResolveOrderOriginAccountUseCase()
        )

    def execute(
        self,
        dto: OrderStatusDTO,
        ingress_project: Project,
        lookup_project: ProjectLookup,
    ) -> Project:
        """Return the destination project for ``dto``.

        Args:
            dto: Incoming order payload.
            ingress_project: Project resolved from the account that received
                the webhook.
            lookup_project: Callable that finds a project by ``vtex_account``.
        """
        if not project_has_multiple_vtex_accounts(ingress_project):
            return ingress_project

        origin_account = self.origin_account_resolver.execute(
            order_id=dto.orderId,
            ingress_vtex_account=dto.vtexAccount,
            ingress_project=ingress_project,
        )
        if not origin_account or origin_account == dto.vtexAccount:
            return ingress_project

        target = lookup_project(origin_account)
        if target is None:
            logger.warning(
                f"[ORDER_STATUS] origin_project_not_found: "
                f"ingress={dto.vtexAccount} origin={origin_account} "
                f"order_id={dto.orderId} ingress_project={ingress_project.uuid}"
            )
            return ingress_project

        logger.info(
            f"[ORDER_STATUS] routed_by_hostname: ingress={dto.vtexAccount} "
            f"origin={origin_account} ingress_project={ingress_project.uuid} "
            f"target_project={target.uuid} order_id={dto.orderId}"
        )
        return target
