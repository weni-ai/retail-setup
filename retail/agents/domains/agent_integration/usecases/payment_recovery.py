import logging
from decimal import Decimal
from typing import Dict, Any, Optional, Tuple
from uuid import UUID

from rest_framework.exceptions import NotFound, ValidationError

from retail.agents.domains.agent_execution.services.logger import ExecutionLoggerService
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.agents.domains.agent_webhook.usecases.order_status import (
    AgentOrderStatusUpdateUsecase,
)
from retail.agents.shared.cache import AgentRole
from retail.agents.shared.vtex_order_value import (
    fetch_order_amount_details,
    propagate_order_amount_to_execution_log,
)
from retail.interfaces.services.execution_logger import (
    ExecutionLoggerServiceInterface,
)
from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.resolve_order_origin_account import (
    ResolveOrderOriginAccountUseCase,
)
from retail.vtex.usecases.resolve_order_origin_project import (
    ProjectLookup,
    ResolveOrderOriginProjectUseCase,
)
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO

logger = logging.getLogger(__name__)


DEFAULT_DELAY_MINUTES = 5


class PaymentRecoveryWebhookUseCase:
    """Use case for processing payment recovery webhook notifications from VTEX."""

    def __init__(
        self,
        vtex_io_service: Optional[VtexIOService] = None,
        exec_logger: Optional[ExecutionLoggerServiceInterface] = None,
        origin_account_resolver: Optional[ResolveOrderOriginAccountUseCase] = None,
        project_resolver: Optional[ResolveOrderOriginProjectUseCase] = None,
        agent_lookup: Optional[BaseAgentWebhookUseCase] = None,
    ):
        """Initialize the use case with its VTEX IO dependency.

        Args:
            vtex_io_service: Service used to fetch order details from VTEX.
                Defaults to a concrete ``VtexIOService`` instance.
            exec_logger: Optional execution logger for agent-logs tracing.
                When omitted, a default ``ExecutionLoggerService`` is used
                (relies on the active execution contextvar when present).
            origin_account_resolver: OMS hostname lookup. When omitted, built
                with the same ``vtex_io_service`` so amount and origin share
                one injected client.
            project_resolver: Resolves the origin project from OMS hostname.
            agent_lookup: Looks up the payment-recovery agent on a project.
        """
        self.vtex_io_service = vtex_io_service or VtexIOService()
        self.exec_logger: ExecutionLoggerServiceInterface = (
            exec_logger or ExecutionLoggerService()
        )
        self.project_resolver = project_resolver or ResolveOrderOriginProjectUseCase(
            origin_account_resolver=origin_account_resolver
            or ResolveOrderOriginAccountUseCase(vtex_io_service=self.vtex_io_service)
        )
        self.agent_lookup = agent_lookup or BaseAgentWebhookUseCase()

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
        """Adapt the PIX hook into the shared order-event dispatcher.

        Payment recovery has no separate lambda pipeline. The hook is
        converted to ``OrderStatusDTO`` with ``currentState="payment-pending"``
        and handed to ``AgentOrderStatusUpdateUsecase.execute`` together with
        the payment-recovery ``IntegratedAgent``. That use case does not look
        up the order-status agent; it dispatches whoever is passed in.

        The raw VTEX state (often ``"unknow"``) is stored as ``lastState``
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

        order_details = propagate_order_amount_to_execution_log(
            self.exec_logger,
            self.vtex_io_service,
            order_id=order_id,
            vtex_account=vtex_account,
            log_prefix="[PAYMENT_RECOVERY]",
        )

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

        dispatch_usecase = AgentOrderStatusUpdateUsecase(
            exec_logger=self.exec_logger,
            vtex_io_service=self.vtex_io_service,
        )
        integrated_agent, vtex_account = self._resolve_origin_agent(
            ingress_agent=integrated_agent,
            dto=order_status_dto,
            lookup_project=dispatch_usecase.get_project_by_vtex_account,
        )
        order_status_dto.vtexAccount = vtex_account
        agent_uuid = integrated_agent.uuid

        if self._is_below_minimum_order_value(
            integrated_agent,
            order_id,
            vtex_account,
            order_value=order_details.amount,
            minimum_value=integrated_agent.config.get("payment_recovery", {}).get(
                "minimum_order_value"
            ),
        ):
            self.exec_logger.log_execution_skip(
                reason="order_value_below_minimum",
                skip_data={
                    "order_id": order_id,
                    "order_value": (
                        str(order_details.amount)
                        if order_details.amount is not None
                        else None
                    ),
                    "minimum_order_value": integrated_agent.config.get(
                        "payment_recovery", {}
                    ).get("minimum_order_value"),
                    "vtex_account": vtex_account,
                },
            )
            return {
                "status": "skipped",
                "message": "Order value below configured minimum",
            }

        dispatch_usecase.execute(
            integrated_agent,
            order_status_dto,
            order_amount_details=order_details,
        )

        logger.info(
            f"[PAYMENT_RECOVERY] completed: "
            f"vtex_account={vtex_account} agent_uuid={agent_uuid} "
            f"current_state=payment-pending order_id={order_id}"
        )

        return {
            "status": "success",
            "message": "Payment recovery notification processed",
        }

    def _resolve_origin_agent(
        self,
        ingress_agent: IntegratedAgent,
        dto: OrderStatusDTO,
        lookup_project: ProjectLookup,
    ) -> Tuple[IntegratedAgent, str]:
        """Return the payment-recovery agent of the order's origin sub-account.

        When the origin project has no active payment-recovery agent, keep the
        ingress agent so the event is not dropped.
        """
        ingress_project = ingress_agent.project
        target_project = self.project_resolver.execute(
            dto=dto,
            ingress_project=ingress_project,
            lookup_project=lookup_project,
        )
        if self._is_same_project(target_project, ingress_project):
            return ingress_agent, ingress_project.vtex_account

        target_agent = self.agent_lookup.get_integrated_agent_if_exists(
            target_project, AgentRole.PAYMENT_RECOVERY
        )
        if target_agent is None:
            logger.warning(
                f"[PAYMENT_RECOVERY] origin_agent_not_found: "
                f"ingress={ingress_project.vtex_account} "
                f"origin={target_project.vtex_account} "
                f"order_id={dto.orderId} ingress_agent={ingress_agent.uuid}"
            )
            return ingress_agent, ingress_project.vtex_account

        logger.info(
            f"[PAYMENT_RECOVERY] routed_by_hostname: "
            f"ingress={ingress_project.vtex_account} "
            f"origin={target_project.vtex_account} "
            f"ingress_agent={ingress_agent.uuid} target_agent={target_agent.uuid} "
            f"order_id={dto.orderId}"
        )
        return target_agent, target_project.vtex_account

    @staticmethod
    def _is_same_project(project: Project, other: Project) -> bool:
        if project is other:
            return True
        project_uuid = getattr(project, "uuid", None)
        other_uuid = getattr(other, "uuid", None)
        return project_uuid is not None and project_uuid == other_uuid

    def _is_below_minimum_order_value(
        self,
        integrated_agent: IntegratedAgent,
        order_id: Optional[str],
        vtex_account: str,
        # Keyword-only from here: order_value/minimum_value must be passed by name.
        *,
        order_value: Optional[Decimal] = None,
        minimum_value: Optional[float] = None,
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
            order_value: Pre-resolved order total in major units, when available.
            minimum_value: Configured minimum order value threshold.

        Returns:
            bool: ``True`` when the dispatch must be skipped because the order
            value is below the configured minimum, ``False`` otherwise.
        """
        if minimum_value is None:
            return False

        if order_value is None:
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
        details = fetch_order_amount_details(
            self.vtex_io_service,
            order_id=order_id,
            vtex_account=vtex_account,
            log_prefix="[PAYMENT_RECOVERY]",
        )
        return details.amount
