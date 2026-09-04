import logging
from typing import Optional
from uuid import UUID

from retail.agents.domains.agent_execution.services.logger import ExecutionLoggerService
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_webhook.usecases.base_agent_webhook import (
    BaseAgentWebhookUseCase,
)
from retail.agents.domains.agent_webhook.usecases.webhook import AgentWebhookUseCase
from retail.agents.shared.cache import AgentRole, IntegratedAgentCacheHandler
from retail.interfaces.services.execution_logger import (
    ExecutionLoggerServiceInterface,
)
from retail.projects.models import Project
from retail.vtex.usecases.resolve_storefront_origin import resolve_storefront_origin
from retail.webhooks.vtex.usecases.dto import (
    BackInStockLambdaPayload,
    ProcessBackInStockNotificationDTO,
    ProcessBackInStockNotificationResult,
)
from retail.webhooks.vtex.usecases.exceptions import BackInStockSendNotReadyError


logger = logging.getLogger(__name__)

DISCARD_AGENT_INACTIVE = "Agent is not active for this account."
DISCARD_NOT_DISPATCHED = "Lambda did not dispatch a send."
NOTIFICATION_SENT = "Notification sent."


class ProcessBackInStockNotificationUseCase(BaseAgentWebhookUseCase):
    """Process a queued back-in-stock notification.

    Runs in the Celery worker, not in the HTTP request. Inactive agents
    are discarded without retry. A failed WhatsApp send raises so Celery
    can surface the error; the IO webhook already answered 200.
    """

    def __init__(
        self,
        account: str,
        cache_handler: Optional[IntegratedAgentCacheHandler] = None,
        exec_logger: Optional[ExecutionLoggerServiceInterface] = None,
        agent_webhook: Optional[AgentWebhookUseCase] = None,
    ) -> None:
        super().__init__(cache_handler=cache_handler)
        self.account = account
        self._exec_logger = exec_logger
        self._agent_webhook = agent_webhook

    @classmethod
    def from_vtex_account(
        cls,
        account: str,
        exec_logger: Optional[ExecutionLoggerServiceInterface] = None,
    ) -> "ProcessBackInStockNotificationUseCase":
        return cls(account=account, exec_logger=exec_logger)

    def execute(
        self, dto: ProcessBackInStockNotificationDTO
    ) -> ProcessBackInStockNotificationResult:
        log_context = self._log_context(dto)
        logger.info(f"[BACK_IN_STOCK] Processing notification: {log_context}")

        project = self.get_project_by_vtex_account(self.account)
        if project is None:
            logger.info(
                f"[BACK_IN_STOCK] Discarding inactive: {log_context} "
                f"reason=project_not_found"
            )
            return ProcessBackInStockNotificationResult(
                discarded=True, reason=DISCARD_AGENT_INACTIVE
            )

        log_context = f"{log_context} project_uuid={project.uuid}"
        integrated_agent = self.get_integrated_agent_if_exists(
            project, AgentRole.BACK_IN_STOCK
        )
        if integrated_agent is None:
            logger.info(
                f"[BACK_IN_STOCK] Discarding inactive: {log_context} "
                f"reason=agent_inactive"
            )
            return ProcessBackInStockNotificationResult(
                discarded=True, reason=DISCARD_AGENT_INACTIVE
            )

        payload = self._build_lambda_payload(dto, project, log_context)
        dispatched = self._start_agent_flow(dto, payload, integrated_agent, log_context)
        if not dispatched:
            return ProcessBackInStockNotificationResult(
                discarded=True, reason=DISCARD_NOT_DISPATCHED
            )
        return ProcessBackInStockNotificationResult(
            discarded=False, reason=NOTIFICATION_SENT
        )

    def _build_lambda_payload(
        self,
        dto: ProcessBackInStockNotificationDTO,
        project: Project,
        log_context: str,
    ) -> BackInStockLambdaPayload:
        storefront = resolve_storefront_origin(project)
        if storefront.used_default:
            logger.info(
                f"[BACK_IN_STOCK] Store was not defined on the project, "
                f"sending the default for this agent: "
                f"{log_context} store={storefront.origin}"
            )
        return BackInStockLambdaPayload(
            sku_id=dto.sku_id,
            client_name=dto.name,
            phone_number=dto.phone,
            store=storefront.origin,
            seller=dto.seller,
            sales_channel=dto.sales_channel,
        )

    def _start_agent_flow(
        self,
        dto: ProcessBackInStockNotificationDTO,
        payload: BackInStockLambdaPayload,
        integrated_agent: IntegratedAgent,
        log_context: str,
    ) -> bool:
        """Invoke the agent lambda. Return True when it dispatched a send.

        A ``None`` result means the lambda decided not to send (e.g. the
        offer is out of stock): the waiter stays pending for the next
        restock, so this is a skip, not a failure. Only an actual
        exception is raised, so the Celery task can surface infra errors.
        """
        exec_logger = self._exec_logger or ExecutionLoggerService()
        webhook = self._agent_webhook or AgentWebhookUseCase(exec_logger=exec_logger)
        lambda_payload = payload.to_lambda_dict()
        execution_uuid = exec_logger.log_webhook_received(
            integrated_agent=integrated_agent,
            payload=lambda_payload,
            contact_urn=f"whatsapp:{dto.phone}",
        )
        try:
            result = webhook.execute_from_task(
                integrated_agent_uuid=str(integrated_agent.uuid),
                payload=lambda_payload,
                params={},
                forwarded_execution_uuid=_as_optional_uuid(execution_uuid),
            )
        except Exception as exc:
            logger.error(f"[BACK_IN_STOCK] Send failed: {log_context} error={exc}")
            raise BackInStockSendNotReadyError(
                "Back in stock WhatsApp send failed."
            ) from exc

        if result is None:
            logger.info(
                f"[BACK_IN_STOCK] Send skipped: {log_context} "
                f"reason=lambda_or_broadcast_did_not_dispatch"
            )
            return False

        logger.info(f"[BACK_IN_STOCK] Sent: {log_context}")
        return True

    def _log_context(self, dto: ProcessBackInStockNotificationDTO) -> str:
        return f"vtex_account={self.account} sku_id={dto.sku_id}"


def _as_optional_uuid(value: Optional[UUID]) -> Optional[UUID]:
    """Drop non-UUID logger no-ops (disabled logging returns None)."""
    return value if isinstance(value, UUID) else None
