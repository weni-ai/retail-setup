import logging
from typing import Callable, Optional

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.cache import AgentRole, IntegratedAgentCacheHandler
from retail.vtex.usecases.phone_number_normalizer import PhoneNumberNormalizer
from retail.webhooks.vtex.usecases.cart import CartUseCase
from retail.webhooks.vtex.usecases.dto import (
    ProcessAbandonedCartNotificationDTO,
    ProcessAbandonedCartNotificationResult,
)
from retail.webhooks.vtex.usecases.exceptions import (
    IntegrationNotConfiguredError,
    InvalidIntegratedAgentError,
    ProjectNotFoundError,
)


logger = logging.getLogger(__name__)


class ProcessAbandonedCartNotificationUseCase:
    """Orchestrate abandoned cart notification processing for all entry points."""

    def __init__(
        self,
        account: Optional[str] = None,
        integrated_agent: Optional[IntegratedAgent] = None,
        cart_use_case_factory: Optional[Callable[..., CartUseCase]] = None,
    ):
        if integrated_agent is not None:
            self.account = integrated_agent.project.vtex_account
            self.pinned_integrated_agent = integrated_agent
        elif account is not None:
            self.account = account
            self.pinned_integrated_agent = None
        else:
            raise ValueError("Either account or integrated_agent must be provided.")

        self._cart_use_case_factory = cart_use_case_factory or CartUseCase

    @classmethod
    def from_vtex_account(
        cls, account: str
    ) -> "ProcessAbandonedCartNotificationUseCase":
        return cls(account=account)

    @classmethod
    def from_integrated_agent(
        cls, integrated_agent: IntegratedAgent
    ) -> "ProcessAbandonedCartNotificationUseCase":
        cls._validate_integrated_agent(integrated_agent)
        return cls(integrated_agent=integrated_agent)

    @staticmethod
    def _validate_integrated_agent(integrated_agent: IntegratedAgent) -> None:
        if not integrated_agent.is_active:
            raise InvalidIntegratedAgentError(
                f"Integrated agent is inactive: {integrated_agent.uuid}"
            )

        if integrated_agent.project.is_blocked:
            raise InvalidIntegratedAgentError(
                f"Project is blocked for integrated agent: {integrated_agent.uuid}"
            )

        role = IntegratedAgentCacheHandler.resolve_role(integrated_agent)
        if role != AgentRole.ABANDONED_CART:
            raise InvalidIntegratedAgentError(
                f"Integrated agent is not an abandoned cart agent: {integrated_agent.uuid}"
            )

    def execute(
        self, dto: ProcessAbandonedCartNotificationDTO
    ) -> ProcessAbandonedCartNotificationResult:
        phone = PhoneNumberNormalizer.normalize(dto.phone)
        log_context = (
            f"vtex_account={self.account} order_form={dto.order_form_id} phone={phone}"
        )

        logger.info(
            f"[CART_WEBHOOK] Processing abandoned cart notification: {log_context}"
        )

        cart_use_case = self._cart_use_case_factory(
            account=self.account,
            pinned_integrated_agent=self.pinned_integrated_agent,
        )

        if cart_use_case.project is None:
            logger.warning(
                f"[CART_WEBHOOK] Project not found: {log_context} "
                f"reason=no_project_for_vtex_account"
            )
            raise ProjectNotFoundError(
                f"Project not found for VTEX account: {self.account}"
            )

        project_uuid = str(cart_use_case.project.uuid)
        log_context = f"{log_context} project_uuid={project_uuid}"

        if not cart_use_case.integrated_agent and not cart_use_case.integrated_feature:
            logger.info(
                f"[CART_WEBHOOK] Integration not configured: {log_context} "
                f"reason=no_integrated_agent_or_feature"
            )
            raise IntegrationNotConfiguredError(
                "Abandoned cart integration not configured for this account."
            )

        integration_type = "agent" if cart_use_case.integrated_agent else "feature"
        integration_uuid = str(
            cart_use_case.integrated_agent.uuid
            if cart_use_case.integrated_agent
            else cart_use_case.integrated_feature.uuid
        )
        logger.info(
            f"[CART_WEBHOOK] Processing cart: {log_context} "
            f"integration_type={integration_type} integration_uuid={integration_uuid}"
        )

        cart = cart_use_case.process_cart_notification(
            dto.order_form_id, phone, dto.name
        )

        logger.info(
            f"[CART_WEBHOOK] Cart processed: {log_context} "
            f"cart_uuid={cart.uuid} cart_status={cart.status}"
        )

        return ProcessAbandonedCartNotificationResult(
            cart_uuid=str(cart.uuid),
            cart_id=str(cart.order_form_id),
            status=cart.status,
            integration_type=integration_type,
            integration_uuid=integration_uuid,
            project_uuid=project_uuid,
            vtex_account=self.account,
        )
