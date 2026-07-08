import logging
from decimal import Decimal
from typing import Dict, Any, Optional
from uuid import UUID

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.services.vtex_io.service import VtexIOService
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

logger = logging.getLogger(__name__)


DEFAULT_DELAY_MINUTES = 5


class PaymentRecoveryWebhookUseCase:
    """Use case for processing payment recovery webhook notifications from VTEX."""

    def __init__(self, vtex_io_service: Optional[VtexIOService] = None):
        """Initialize the use case with its VTEX IO dependency.

        Args:
            vtex_io_service: Service used to fetch order details from VTEX.
                Defaults to a concrete ``VtexIOService`` instance.
        """
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        """Retrieve an active integrated agent by UUID.

        Args:
            integrated_agent_uuid: UUID of the integrated agent.

        Returns:
            IntegratedAgent: The matching active integrated agent instance.

        Raises:
            NotFound: If no active integrated agent exists with the given UUID.
        """
        try:
            return IntegratedAgent.objects.select_related("project").get(
                uuid=integrated_agent_uuid,
                is_active=True,
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(
                f"Active integrated agent not found: {integrated_agent_uuid}"
            )

    def get_delay_seconds(
        self,
        integrated_agent_uuid: UUID,
        integrated_agent: Optional[IntegratedAgent] = None,
    ) -> int:
        """Get the configured delay in seconds for scheduling the processing task.

        Reads ``delay_minutes`` from ``integrated_agent.config["payment_recovery"]``
        and falls back to ``DEFAULT_DELAY_MINUTES`` when the agent is inactive,
        missing, or the config is absent.

        Args:
            integrated_agent_uuid: UUID of the integrated agent.
            integrated_agent: Optional pre-resolved active integrated agent.

        Returns:
            int: The delay in seconds before processing the webhook.
        """
        if integrated_agent is None:
            try:
                integrated_agent = self.get_integrated_agent(integrated_agent_uuid)
            except NotFound:
                return DEFAULT_DELAY_MINUTES * 60

        payment_config = integrated_agent.config.get("payment_recovery", {})
        delay_minutes = payment_config.get("delay_minutes", DEFAULT_DELAY_MINUTES)
        return int(delay_minutes) * 60

    def validate_payment_recovery_enabled(
        self, integrated_agent: IntegratedAgent
    ) -> None:
        """Validate that payment recovery is enabled for the integrated agent.

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
        """Process a VTEX payment recovery webhook notification.

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

        return self._process_payment_recovery_notification(
            integrated_agent, webhook_data, vtex_account
        )

    def _process_payment_recovery_notification(
        self,
        integrated_agent: IntegratedAgent,
        webhook_data: Dict[str, Any],
        vtex_account: str,
    ) -> Dict[str, str]:
        """Build an OrderStatusDTO and delegate to AgentOrderStatusUpdateUsecase.

        The DTO is built with ``currentState="payment-pending"``. The raw
        VTEX state (often ``"unknow"``) is stored as ``lastState``
        while ``currentState`` is hardcoded because the payment recovery
        hook only fires for orders awaiting payment.

        Args:
            integrated_agent: The integrated agent that owns the webhook.
            webhook_data: Raw data received from the VTEX webhook.
            vtex_account: The VTEX account identifier for the project.

        Returns:
            Dict[str, str]: ``status``/``message`` describing whether the
            notification was dispatched or skipped below the minimum value.
        """
        agent_uuid = integrated_agent.uuid
        order_id = webhook_data.get("OrderId")

        if self._is_below_minimum_order_value(integrated_agent, order_id, vtex_account):
            return {
                "status": "skipped",
                "message": "Order value below configured minimum",
            }

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

        return {
            "status": "success",
            "message": "Payment recovery notification processed",
        }

    def _is_below_minimum_order_value(
        self,
        integrated_agent: IntegratedAgent,
        order_id: Optional[str],
        vtex_account: str,
    ) -> bool:
        """Decide whether the recovery dispatch must be skipped by minimum value.

        No threshold (``minimum_order_value`` is ``None`` or absent) means
        every recovery request is dispatched. When a threshold is set but the
        order value cannot be resolved from VTEX, the dispatch proceeds to
        avoid dropping a legitimate recovery on a transient lookup failure.

        Args:
            integrated_agent: The integrated agent that owns the webhook.
            order_id: VTEX order identifier from the webhook payload.
            vtex_account: The VTEX account identifier for the project.

        Returns:
            bool: ``True`` when the dispatch must be skipped because the order
            value is below the configured minimum, ``False`` otherwise.
        """
        payment_config = integrated_agent.config.get("payment_recovery", {})
        minimum_value = payment_config.get("minimum_order_value")

        if minimum_value is None:
            return False

        order_value = self._get_order_value(order_id, vtex_account)
        if order_value is None:
            logger.warning(
                f"[PAYMENT_RECOVERY] minimum_value_unresolved: "
                f"vtex_account={vtex_account} agent_uuid={integrated_agent.uuid} "
                f"order_id={order_id} minimum_order_value={minimum_value} "
                f"action=dispatch reason=order_value_unavailable"
            )
            return False

        if order_value < Decimal(str(minimum_value)):
            logger.info(
                f"[PAYMENT_RECOVERY] skipped_below_minimum_value: "
                f"vtex_account={vtex_account} agent_uuid={integrated_agent.uuid} "
                f"order_id={order_id} order_value={order_value} "
                f"minimum_order_value={minimum_value}"
            )
            return True

        return False

    def _get_order_value(
        self, order_id: Optional[str], vtex_account: str
    ) -> Optional[Decimal]:
        """Resolve the order total (in major units) from the VTEX order details.

        VTEX returns ``order.value`` in minor units (cents), so the value is
        divided by 100 and rounded to two decimal places.

        Args:
            order_id: VTEX order identifier from the webhook payload.
            vtex_account: The VTEX account identifier for the project.

        Returns:
            Optional[Decimal]: The order total in major units, or ``None`` when
            the order id is missing, the lookup fails or the value is absent.

        Example:
            A VTEX ``value`` of ``2047`` (cents) resolves to
            ``Decimal("20.47")`` (R$ 20.47).
        """
        if not order_id:
            return None

        account_domain = f"{vtex_account}.myvtex.com"
        try:
            order_details = self.vtex_io_service.get_order_details_by_id(
                account_domain=account_domain,
                vtex_account=vtex_account,
                order_id=order_id,
            )
        except Exception as exc:
            logger.warning(
                f"[PAYMENT_RECOVERY] order_lookup_failed: "
                f"vtex_account={vtex_account} order_id={order_id} error={exc}"
            )
            return None

        if not order_details:
            return None

        raw_value = order_details.get("value")
        if raw_value in (None, ""):
            return None

        try:
            return (Decimal(raw_value) / Decimal(100)).quantize(Decimal("0.01"))
        except (TypeError, ValueError, ArithmeticError):
            return None
