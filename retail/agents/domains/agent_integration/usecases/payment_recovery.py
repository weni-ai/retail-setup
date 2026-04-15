import logging
from typing import Dict, Any
from uuid import UUID

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

logger = logging.getLogger(__name__)


DEFAULT_DELAY_MINUTES = 10


class PaymentRecoveryWebhookUseCase:
    """Use case for processing payment recovery webhook notifications from VTEX."""

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(uuid=integrated_agent_uuid)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {integrated_agent_uuid}")

    def get_delay_seconds(self, integrated_agent_uuid: UUID) -> int:
        """
        Get the configured delay in seconds for scheduling the processing task.

        Reads delay_minutes from integrated_agent.config["payment_recovery"].
        Falls back to DEFAULT_DELAY_MINUTES if agent or config is not found.
        """
        try:
            integrated_agent = IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
            payment_config = integrated_agent.config.get("payment_recovery", {})
            delay_minutes = payment_config.get("delay_minutes", DEFAULT_DELAY_MINUTES)
            return int(delay_minutes) * 60
        except IntegratedAgent.DoesNotExist:
            return DEFAULT_DELAY_MINUTES * 60

    def validate_payment_recovery_enabled(
        self, integrated_agent: IntegratedAgent
    ) -> None:
        payment_config = integrated_agent.config.get("payment_recovery", {})
        if not payment_config.get("hook_created", False):
            raise ValidationError("Payment recovery hook not configured")

    def process_webhook_notification(
        self, integrated_agent: IntegratedAgent, webhook_data: Dict[str, Any]
    ) -> Dict[str, str]:
        """
        Process a VTEX payment recovery webhook notification.

        Validates that payment recovery is enabled, builds an OrderStatusDTO
        and delegates to AgentOrderStatusUpdateUsecase — same pattern as
        DeliveredOrderTrackingWebhookUseCase.
        """
        self.validate_payment_recovery_enabled(integrated_agent)

        logger.info(
            f"[PaymentRecovery] Processing webhook notification - "
            f"agent={integrated_agent.uuid} data={webhook_data}"
        )

        self._process_payment_recovery_notification(integrated_agent, webhook_data)

        return {
            "status": "success",
            "message": "Payment recovery notification processed",
        }

    def _process_payment_recovery_notification(
        self, integrated_agent: IntegratedAgent, webhook_data: Dict[str, Any]
    ) -> None:
        vtex_account = integrated_agent.project.vtex_account

        order_status_dto = OrderStatusDTO(
            recorder={},
            domain="OrdersDocumentUpdated",
            orderId=webhook_data.get("OrderId"),
            currentState="payment-pending",
            lastState=webhook_data.get("State"),
            currentChangeDate=webhook_data.get("CurrentChange"),
            lastChangeDate=webhook_data.get("LastChange"),
            vtexAccount=vtex_account,
        )

        logger.info(
            f"[PaymentRecovery] OrderStatusDTO built - "
            f"agent={integrated_agent.uuid} order_id={order_status_dto.orderId}"
        )

        order_status_usecase = AgentOrderStatusUpdateUsecase()
        order_status_usecase.execute(integrated_agent, order_status_dto)

        logger.info(
            f"[PaymentRecovery] Webhook processed successfully - "
            f"agent={integrated_agent.uuid} order_id={order_status_dto.orderId}"
        )
