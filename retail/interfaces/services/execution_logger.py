"""Port for the high-level execution logger.

Consumers (the agent webhook use case, the cart abandonment service,
the VTEX order-status use case, several Celery tasks) depend on this
Protocol so the concrete service can be swapped without touching call
sites.
"""

from decimal import Decimal
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ExecutionLoggerServiceInterface(Protocol):
    """Contract for the high-level execution logger."""

    def log_webhook_received(
        self,
        integrated_agent: Optional[Any],
        payload: Dict[str, Any],
        contact_urn: Optional[str] = None,
        order_id: Optional[str] = None,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
    ) -> UUID:
        """Open a new execution row and return its UUID."""
        ...

    def log_lambda_request(
        self,
        request_data: Dict[str, Any],
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """Append a Lambda-request trace to the active execution."""
        ...

    def log_lambda_response(
        self,
        response_data: Dict[str, Any],
        execution_uuid: Optional[UUID] = None,
        log_tail: Optional[str] = None,
    ) -> None:
        """Append a Lambda-response trace to the active execution."""
        ...

    def log_broadcast_sent(
        self,
        broadcast_response: Dict[str, Any],
        template_uuid: Optional[UUID] = None,
        broadcast_id: Optional[int] = None,
        broadcast_message_uuid: Optional[UUID] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """Mark the execution as ``success`` and emit a broadcast trace."""
        ...

    def log_execution_error(
        self,
        error_message: str,
        error_data: Optional[Dict[str, Any]] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """Mark the execution as ``error`` and emit an error trace."""
        ...

    def log_execution_skip(
        self,
        reason: str,
        skip_data: Optional[Dict[str, Any]] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """Mark the execution as ``skip`` and emit a skip trace."""
        ...

    def update_contact_urn(
        self,
        contact_urn: str,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """Update the contact URN on the active execution row."""
        ...

    def update_order_info(
        self,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
        execution_uuid: Optional[UUID] = None,
    ) -> None:
        """Update the order amount/currency on the active execution row."""
        ...
