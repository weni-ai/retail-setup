"""Execution Logger Service.

High-level API for logging agent executions. Provides simple methods
for logging different stages of execution (webhook received, lambda
invoked, broadcast sent, etc.).

Uses contextvars to automatically track execution context without
requiring explicit ``execution_uuid`` passing through method
signatures.
"""

import functools
import logging
from decimal import Decimal
from typing import Any, Callable, Dict, Optional
from uuid import UUID

from retail.agents.domains.agent_execution.constants import (
    LEGACY_FLOW_AGENT_LABEL,
    UNKNOWN_CONTACT_URN,
)
from retail.agents.domains.agent_execution.context import (
    get_current_execution_uuid,
    set_current_execution_uuid,
)
from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.services.buffer import ExecutionBufferService
from retail.agents.domains.agent_execution.types import ExecutionTraceType
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.interfaces.services.execution_logger import (
    ExecutionLoggerServiceInterface,
)


logger = logging.getLogger(__name__)


def _with_execution_uuid(method: Callable) -> Callable:
    """Resolve the active execution UUID before calling ``method``.

    Methods that emit traces share the same three-line preamble:
    pick up the ``execution_uuid`` kwarg, fall back to the contextvar,
    bail when neither is set. This decorator collapses that into a
    single ``exec_uuid`` keyword argument that the wrapped method
    consumes alongside the rest of its kwargs.
    """

    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        execution_uuid = kwargs.pop("execution_uuid", None)
        exec_uuid = self._get_execution_uuid(execution_uuid)
        if not exec_uuid:
            return None
        return method(self, *args, exec_uuid=exec_uuid, **kwargs)

    return wrapper


class ExecutionLoggerService(ExecutionLoggerServiceInterface):
    """High-level service for logging agent executions.

    Provides a simple API for logging different stages of execution:
    webhook received, lambda request/response, broadcast sent, errors
    and skips.

    Design notes
    ------------
    No module-level singleton or ``get_execution_logger()`` factory by
    design. Composition roots (Celery tasks, views) instantiate this
    class directly and inject it into use cases/services via
    constructor. Per-execution state lives in contextvars (see
    ``agent_execution/context.py``); the boto3 S3 client is shared at
    the buffer level (see ``_shared_traces_storage`` in
    ``buffer.py``).
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
        """Log the start of an execution when a webhook is received.

        Also sets the execution_uuid in context so subsequent logging
        calls can access it without explicit parameter passing.
        """
        if not contact_urn:
            contact_urn = self._extract_contact_urn(payload)

        integrated_agent_uuid = integrated_agent.uuid if integrated_agent else None

        execution_uuid = self.buffer.start_execution(
            integrated_agent_uuid=integrated_agent_uuid,
            contact_urn=contact_urn or UNKNOWN_CONTACT_URN,
            webhook_payload=payload,
            order_id=order_id,
            amount=amount,
            currency=currency,
        )

        set_current_execution_uuid(execution_uuid)

        agent_info = (
            integrated_agent.uuid if integrated_agent else LEGACY_FLOW_AGENT_LABEL
        )
        logger.info(
            f"[EXEC_LOG] Started execution {execution_uuid} for agent {agent_info}"
        )
        return execution_uuid

    def _get_execution_uuid(
        self, execution_uuid: Optional[UUID] = None
    ) -> Optional[UUID]:
        """Return the provided UUID or fall back to the context-bound one."""
        return execution_uuid or get_current_execution_uuid()

    @_with_execution_uuid
    def log_lambda_request(
        self,
        request_data: Dict[str, Any],
        *,
        exec_uuid: UUID,
    ) -> None:
        """Log the lambda invocation request."""
        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.LAMBDA_REQUEST.value,
            data=request_data,
        )
        logger.info(f"[EXEC_LOG] Logged lambda request for execution {exec_uuid}")

    @_with_execution_uuid
    def log_lambda_response(
        self,
        response_data: Dict[str, Any],
        *,
        exec_uuid: UUID,
        log_tail: Optional[str] = None,
    ) -> None:
        """Log the lambda invocation response.

        ``log_tail`` is the optional decoded tail (~4 KB) of Lambda
        stdout/stderr returned via ``LogType="Tail"``. When provided,
        it is attached to the trace under ``lambda_log_tail`` so prints
        from the function surface alongside the response.
        """
        trace_data: Dict[str, Any] = dict(response_data) if response_data else {}
        if log_tail:
            trace_data["lambda_log_tail"] = log_tail

        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.LAMBDA_RESPONSE.value,
            data=trace_data,
        )
        logger.info(f"[EXEC_LOG] Logged lambda response for execution {exec_uuid}")

    @_with_execution_uuid
    def log_broadcast_sent(
        self,
        broadcast_response: Dict[str, Any],
        *,
        exec_uuid: UUID,
        template_uuid: Optional[UUID] = None,
        broadcast_id: Optional[int] = None,
        broadcast_message_uuid: Optional[UUID] = None,
    ) -> None:
        """Log a successful broadcast and mark execution as success."""
        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=ExecutionTraceType.BROADCAST_RESPONSE.value,
            data=broadcast_response,
        )

        self.buffer.update_metadata(
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

    def _log_terminal(
        self,
        *,
        exec_uuid: UUID,
        trace_type: str,
        trace_data: Dict[str, Any],
        status: str,
        log_level: int,
        log_summary: str,
        error_message: Optional[str] = None,
    ) -> None:
        """Shared body for terminal log paths (``error`` / ``skip``).

        Both terminal paths emit a trace, update the buffer with the
        terminal status (plus ``error_message`` for the error path),
        and log a single human-readable summary line. Keeping them
        behind one helper guarantees they stay in sync if either path
        grows new behaviour.
        """
        self.buffer.add_trace(
            execution_uuid=exec_uuid,
            trace_type=trace_type,
            data=trace_data,
        )
        update_kwargs: Dict[str, Any] = {
            "execution_uuid": exec_uuid,
            "status": status,
        }
        if error_message is not None:
            update_kwargs["error_message"] = error_message
        self.buffer.update_metadata(**update_kwargs)
        logger.log(log_level, log_summary)

    @_with_execution_uuid
    def log_execution_error(
        self,
        error_message: str,
        *,
        exec_uuid: UUID,
        error_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an execution error and mark the row as terminal.

        Emits the audit line at ``logger.WARNING``. This method is the
        state-transition trail for the ``AgentExecution`` row, not the
        primary error log. Callers (e.g.
        ``task_helpers._log_terminal_error``,
        ``services_cart_abandonment_unified._log_execution_error``,
        ``webhook.execute``) are expected to log the underlying system
        error themselves at ``logger.error`` / ``logger.exception`` so
        Sentry captures the traceback. Keeping this method at
        ``WARNING`` avoids duplicate Sentry events for the same
        failure.
        """
        trace_data: Dict[str, Any] = {"error_message": error_message}
        if error_data:
            trace_data["details"] = error_data
        self._log_terminal(
            exec_uuid=exec_uuid,
            trace_type=ExecutionTraceType.ERROR.value,
            trace_data=trace_data,
            status=AgentExecutionStatus.ERROR,
            log_level=logging.WARNING,
            log_summary=f"[EXEC_LOG] Execution {exec_uuid} failed: {error_message}",
            error_message=error_message,
        )

    @_with_execution_uuid
    def log_execution_skip(
        self,
        reason: str,
        *,
        exec_uuid: UUID,
        skip_data: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Log an execution skip (e.g., contact not allowed, rule not matched)."""
        trace_data: Dict[str, Any] = {"reason": reason}
        if skip_data:
            trace_data["details"] = skip_data
        self._log_terminal(
            exec_uuid=exec_uuid,
            trace_type=ExecutionTraceType.SKIP.value,
            trace_data=trace_data,
            status=AgentExecutionStatus.SKIP,
            log_level=logging.DEBUG,
            log_summary=f"[EXEC_LOG] Execution {exec_uuid} skipped: {reason}",
        )

    @_with_execution_uuid
    def update_contact_urn(
        self,
        contact_urn: str,
        *,
        exec_uuid: UUID,
    ) -> None:
        """Update the contact URN for an execution.

        Useful when contact_urn is not known at webhook time but
        becomes available after lambda processing.
        """
        self.buffer.update_metadata(
            execution_uuid=exec_uuid,
            contact_urn=contact_urn,
        )

    @_with_execution_uuid
    def update_order_info(
        self,
        *,
        exec_uuid: UUID,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
    ) -> None:
        """Update order amount/currency for an execution.

        Useful when the order total/currency is computed after the
        webhook is logged (for example, the cart abandonment service
        calculates the total value during processing). Either field
        can be omitted; the buffer drops ``None`` values rather than
        overwriting existing entries.
        """
        self.buffer.update_metadata(
            execution_uuid=exec_uuid,
            amount=amount,
            currency=currency,
        )

    def _extract_contact_urn(self, payload: Dict[str, Any]) -> Optional[str]:
        """Try to extract contact_urn from common payload locations."""
        if "contact_urn" in payload:
            return payload["contact_urn"]

        if "phone" in payload:
            phone = payload["phone"]
            if not phone.startswith("whatsapp:"):
                return f"whatsapp:{phone}"
            return phone

        # For VTEX order status webhooks, contact is not in the initial payload.
        # It will be set later after lambda processing.
        return None
