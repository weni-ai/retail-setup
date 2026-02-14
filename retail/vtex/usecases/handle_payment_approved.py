"""
Orchestrator for payment-approved events.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.cache import cache

from retail.projects.models import Project
from retail.services.flows.service import FlowsService
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.repositories.cart_repository import CartRepository
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase
from retail.vtex.usecases.handle_purchase_event import HandlePurchaseEventUseCase
from retail.vtex.usecases.handle_abandoned_cart_conversion import (
    HandleAbandonedCartConversionUseCase,
)


logger = logging.getLogger(__name__)


@dataclass
class OrderContext:
    """Shared context for payment-approved handlers."""

    order_id: str
    project: Project
    order_details: dict
    order_form_id: str


class PaymentApprovedOrchestrator:
    """
    Orchestrates payment-approved events by fetching shared data once
    and delegating to specific handlers.
    """

    def __init__(
        self,
        vtex_io_service: Optional[VtexIOService] = None,
        flows_service: Optional[FlowsService] = None,
        cart_repository: Optional[CartRepository] = None,
        jwt_generator: Optional[JWTUsecase] = None,
    ) -> None:
        self.vtex_io_service = vtex_io_service or VtexIOService()
        self.flows_service = flows_service or FlowsService()
        self.cart_repository = cart_repository or CartRepository()
        self.jwt_generator = jwt_generator or JWTUsecase()

    def execute(self, order_id: str, project_uuid: str) -> None:
        """Execute all payment-approved handlers with shared context."""
        log_prefix = f"[PAYMENT_APPROVED] order_id={order_id} project={project_uuid}"

        context = self._build_context(order_id, project_uuid)
        if not context:
            logger.debug(f"{log_prefix} Could not build context, skipping handlers")
            return

        logger.info(
            f"{log_prefix} Context built, order_form_id={context.order_form_id}"
        )

        HandlePurchaseEventUseCase(
            flows_service=self.flows_service,
            cart_repository=self.cart_repository,
            jwt_generator=self.jwt_generator,
        ).execute(context)

        HandleAbandonedCartConversionUseCase(
            flows_service=self.flows_service,
            cart_repository=self.cart_repository,
            jwt_generator=self.jwt_generator,
        ).execute(context)

        logger.info(f"{log_prefix} All handlers executed")

    def _build_context(
        self, order_id: str, project_uuid: str
    ) -> Optional[OrderContext]:
        """Build the shared context by fetching all required data."""
        log_prefix = f"[PAYMENT_APPROVED] order_id={order_id} project={project_uuid}"

        project = self._get_project(project_uuid)
        if not project:
            logger.debug(f"{log_prefix} Project not found")
            return None

        order_details = self._get_order_details(order_id, project)
        if not order_details:
            logger.debug(f"{log_prefix} Order details not found in VTEX")
            return None

        order_form_id = order_details.get("orderFormId")
        if not order_form_id:
            logger.debug(f"{log_prefix} No order_form_id in order details")
            return None

        return OrderContext(
            order_id=order_id,
            project=project,
            order_details=order_details,
            order_form_id=order_form_id,
        )

    def _get_project(self, project_uuid: str) -> Optional[Project]:
        """Fetch the project by UUID, using cache."""
        cache_key = f"project_by_uuid_{project_uuid}"
        project = cache.get(cache_key)

        if project:
            return project

        try:
            project = Project.objects.get(uuid=project_uuid)
            cache.set(cache_key, project, timeout=43200)
            return project
        except Project.DoesNotExist:
            return None
        except Project.MultipleObjectsReturned:
            logger.error(f"Multiple projects found for UUID {project_uuid}")
            return None

    def _get_order_details(self, order_id: str, project: Project) -> Optional[dict]:
        """Retrieve order details from VTEX."""
        account_domain = f"{project.vtex_account}.myvtex.com"
        try:
            return self.vtex_io_service.get_order_details_by_id(
                account_domain=account_domain,
                project_uuid=str(project.uuid),
                order_id=order_id,
            )
        except Exception as e:
            logger.error(f"Error fetching order details: {e}")
            return None
