"""
Execution Logger Service.

High-level API for logging agent executions. Provides simple methods for
logging different stages of execution (webhook received, lambda invoked,
broadcast sent, etc.).

Uses contextvars to automatically track execution context without requiring
explicit execution_uuid passing through method signatures.
"""

import logging
from decimal import Decimal
from typing import Any, Dict, Optional
from uuid import UUID

from retail.agents.domains.agent_execution.context import (
    get_current_execution_uuid,
    set_current_execution_uuid,
)
from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.services.buffer import ExecutionBufferService
from retail.agents.domains.agent_execution.types import ExecutionTraceType
from retail.agents.domains.agent_integration.models import IntegratedAgent


logger = logging.getLogger(__name__)


# No module-level singleton or get_execution_logger() factory by design.
# Composition roots (Celery tasks, views) instantiate this class directly
# and inject it into use cases/services via constructor. Per-execution
# state lives in contextvars (see agent_execution/context.py); the boto3
# S3 client is shared at the buffer level (see _shared_traces_storage in
# buffer.py).
class ExecutionLoggerService:
    """
    High-level service for logging agent executions.

    Provides a simple API for logging different stages of execution:
    - Webhook received (starts execution)
    - Lambda request/response
    - Broadcast sent
    - Errors and skips
    """

    def __init__(self, buffer_service: Optional[ExecutionBufferService] = None):
        self.buffer = buffer_service or ExecutionBufferService()

    def log_webhook_received(
        self,
        integrated_agent: Optional[IntegratedAgent],
        payload: Dict[str, Any],
        contact_urn: Optional[str] = None,
        order_id: Optional[str] = None,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
    ) -> UUID:
        """
        Log the start of an execution when a webhook is received.

        Also sets the execution_uuid in context so subsequent logging calls
        can access it without explicit parameter passing.

        Args:
            integrated_agent: The integrated agent processing the webhook (can be None for legacy flows)
            payload: The webhook payload data
            contact_urn: Contact URN (extracted from payload if not provided)
            order_id: Optional order ID for official agents
            amount: Optional order amount for official agents
            currency: Optional ISO-4217 currency code (e.g., 'BRL', 'USD')

        Returns:
            UUID of the new execution for tracking subsequent events
        """
        if not contact_urn:
            contact_urn = self._extract_contact_urn(payload)

        integrated_agent_uuid = integrated_agent.uuid if integrated_agent else None

        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=integrated_agent_uuid,
            contact_urn=contact_urn or "unknown",
            webhook_payload=payload,
            order_id=order_id,
            amount=amount,
            currency=currency,
        )

        # Set in context for automatic access in downstream calls
        set_current_execution_uuid(execution_uuid)

        agent_info = integrated_agent.uuid if integrated_agent else "legacy_flow"
        logger.info(
            f"[EXEC_LOG] Started execution {execution_uuid} for agent {agent_info}"
        )
        return execution_uuid

    def _get_execution_uuid(
        self, execution_uuid: Optional[UUID] = None
    ) -> Optional[UUID]:
        """Get execution UUID from parameter or context."""
        if execution_uuid:
            return execution_uuid
        return get_current_execution_uuid()

    def log_lambda_request(
        self,
        request_data: Dict[str, Any],
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """
        Log the lambda invocation request.

        Args:
            request_data: The data sent to the lambda function
            execution_uuid: Optional UUID (uses context if not provided)
        """
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return

        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.LAMBDA_REQUEST.value,
            data=request_data,
        )
        logger.debug(f"[EXEC_LOG] Logged lambda request for execution {exec_uuid}")

    def log_lambda_response(
        self,
        response_data: Dict[str, Any],
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """
        Log the lambda invocation response.

        Args:
            response_data: The response from the lambda function
            execution_uuid: Optional UUID (uses context if not provided)
        """
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return

        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.LAMBDA_RESPONSE.value,
            data=response_data,
        )
        logger.debug(f"[EXEC_LOG] Logged lambda response for execution {exec_uuid}")

    def log_broadcast_sent(
        self,
        broadcast_response: Dict[str, Any],
        template_uuid: Optional[UUID] = None,
        broadcast_id: Optional[int] = None,
        broadcast_message_uuid: Optional[UUID] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """
        Log a successful broadcast and mark execution as success.

        Args:
            broadcast_response: Response from the broadcast service
            template_uuid: UUID of the template used
            broadcast_id: ID returned by the broadcast service
            broadcast_message_uuid: UUID of the BroadcastMessage row created
                by ``RecordBroadcastSentUseCase`` at dispatch time. Persisted
                onto ``AgentExecution.broadcast_message`` so the agent-logs
                API can reflect the courier-driven broadcast lifecycle.
            execution_uuid: Optional UUID (uses context if not provided)
        """
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return

        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.BROADCAST_RESPONSE.value,
            data=broadcast_response,
        )

        self.buffer.update_status(
            execution_uuid=exec_uuid,
            status=AgentExecutionStatus.SUCCESS,
            template_uuid=template_uuid,
            broadcast_id=broadcast_id,
            broadcast_message_uuid=broadcast_message_uuid,
        )

        logger.info(
            f"[EXEC_LOG] Execution {exec_uuid} completed successfully "
            f"(broadcast_id={broadcast_id}, "
            f"broadcast_message_uuid={broadcast_message_uuid})"
        )

    def log_execution_error(
        self,
        error_message: str,
        error_data: Optional[Dict[str, Any]] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """
        Log an execution error.

        Args:
            error_message: Description of the error
            error_data: Optional additional error details
            execution_uuid: Optional UUID (uses context if not provided)
        """
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return

        trace_data = {"error_message": error_message}
        if error_data:
            trace_data["details"] = error_data

        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.ERROR.value,
            data=trace_data,
        )

        self.buffer.update_status(
            execution_uuid=exec_uuid,
            status=AgentExecutionStatus.ERROR,
            error_message=error_message,
        )

        logger.warning(f"[EXEC_LOG] Execution {exec_uuid} failed: {error_message}")

    def log_execution_skip(
        self,
        reason: str,
        skip_data: Optional[Dict[str, Any]] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """
        Log an execution skip (e.g., contact not allowed, rule not matched).

        Args:
            reason: Reason for skipping
            skip_data: Optional additional skip details
            execution_uuid: Optional UUID (uses context if not provided)
        """
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return

        trace_data = {"reason": reason}
        if skip_data:
            trace_data["details"] = skip_data

        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.SKIP.value,
            data=trace_data,
        )

        self.buffer.update_status(
            execution_uuid=exec_uuid,
            status=AgentExecutionStatus.SKIP,
        )

        logger.info(f"[EXEC_LOG] Execution {exec_uuid} skipped: {reason}")

    def update_contact_urn(
        self,
        contact_urn: str,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """
        Update the contact URN for an execution.

        Useful when contact_urn is not known at webhook time
        but becomes available after lambda processing.

        Args:
            contact_urn: The contact URN to set
            execution_uuid: Optional UUID (uses context if not provided)
        """
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return

        self.buffer.update_metadata(
            execution_uuid=exec_uuid,
            contact_urn=contact_urn,
        )

    def update_order_info(
        self,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """
        Update order amount/currency for an execution.

        Useful when the order total/currency is computed after the
        webhook is logged (for example, the cart abandonment service
        calculates the total value during processing). Either field
        can be omitted; the buffer drops ``None`` values rather than
        overwriting existing entries.

        Args:
            amount: Order total as a Decimal
            currency: ISO-4217 three-letter code (e.g., 'BRL', 'USD')
            execution_uuid: Optional UUID (uses context if not provided)
        """
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return

        self.buffer.update_metadata(
            execution_uuid=exec_uuid,
            amount=amount,
            currency=currency,
        )

    def _extract_contact_urn(self, payload: Dict[str, Any]) -> Optional[str]:
        """
        Try to extract contact_urn from common payload locations.

        Args:
            payload: The webhook payload

        Returns:
            Extracted contact_urn or None
        """
        # Check common locations for contact URN
        if "contact_urn" in payload:
            return payload["contact_urn"]

        if "phone" in payload:
            phone = payload["phone"]
            if not phone.startswith("whatsapp:"):
                return f"whatsapp:{phone}"
            return phone

        # For VTEX order status webhooks, contact is not in the initial payload
        # It will be set later after lambda processing
        return None
