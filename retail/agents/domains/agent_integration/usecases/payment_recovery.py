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


DEFAULT_DELAY_MINUTES = 5


class PaymentRecoveryWebhookUseCase:
    """Use case for processing payment recovery webhook notifications from VTEX."""

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        """
        Retrieve an integrated agent by UUID.

        Args:
            integrated_agent_uuid: UUID of the integrated agent.

        Returns:
            IntegratedAgent: The matching integrated agent instance.

        Raises:
            NotFound: If no integrated agent exists with the given UUID.
        """
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
        """
        Validate that payment recovery is enabled for the integrated agent.

        Args:
            integrated_agent: The integrated agent to validate.

        Raises:
            ValidationError: If payment recovery hook is not configured.
        """
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

        Args:
            integrated_agent: The integrated agent that owns the webhook.
            webhook_data: Raw data received from the VTEX webhook.

        Returns:
            Dict[str, str]: A dict with ``status`` and ``message`` keys.
        """
        vtex_account = integrated_agent.project.vtex_account
        agent_uuid = integrated_agent.uuid

        self.validate_payment_recovery_enabled(integrated_agent)

        logger.info(
            f"[PAYMENT_RECOVERY] received: "
            f"vtex_account={vtex_account} agent_uuid={agent_uuid} "
            f"data={webhook_data}"
        )

        self._process_payment_recovery_notification(
            integrated_agent, webhook_data, vtex_account
        )

        return {
            "status": "success",
            "message": "Payment recovery notification processed",
        }

    def _process_payment_recovery_notification(
        self,
        integrated_agent: IntegratedAgent,
        webhook_data: Dict[str, Any],
        vtex_account: str,
    ) -> None:
        """
        Build an OrderStatusDTO with ``currentState="payment-pending"``
        and delegate to AgentOrderStatusUpdateUsecase.

        The raw VTEX state (often ``"unknow"``) is stored as ``lastState``
        while ``currentState`` is hardcoded because the payment recovery
        hook only fires for orders awaiting payment.

        Args:
            integrated_agent: The integrated agent that owns the webhook.
            webhook_data: Raw data received from the VTEX webhook.
            vtex_account: The VTEX account identifier for the project.
        """
        agent_uuid = integrated_agent.uuid
        order_id = webhook_data.get("OrderId")

        logger.info(
            f"[PAYMENT_RECOVERY] converting_state: "
            f"vtex_account={vtex_account} agent_uuid={agent_uuid} "
            f"mapped_state=payment-pending data={webhook_data}"
        )

        order_status_dto = OrderStatusDTO(
            recorder={},
            domain="OrdersDocumentUpdated",
            orderId=order_id,
            currentState="payment-pending",
            lastState=webhook_data.get("State"),
            currentChangeDate=webhook_data.get("CurrentChange"),
            lastChangeDate=webhook_data.get("LastChange"),
            vtexAccount=vtex_account,
        )

        order_status_usecase = AgentOrderStatusUpdateUsecase()
        order_status_usecase.execute(integrated_agent, order_status_dto)

        logger.info(
            f"[PAYMENT_RECOVERY] completed: "
            f"vtex_account={vtex_account} agent_uuid={agent_uuid} "
            f"current_state=payment-pending order_id={order_id}"
        )
