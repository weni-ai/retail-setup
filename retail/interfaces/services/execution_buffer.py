"""Port for the Redis-backed agent-execution buffer.

The buffer owns per-execution state during a webhook's lifetime
(initial DB INSERT + Redis hash/list/ZSET). Flush and sweep are use
cases that consume this port — they are not part of the contract.
Consumers (the execution logger, tests) depend on this Protocol so
the concrete adapter can be swapped without touching call sites.
"""

from decimal import Decimal
from typing import Any, Dict, Optional, Protocol, runtime_checkable
from uuid import UUID


@runtime_checkable
class ExecutionBufferInterface(Protocol):
    """Adapter contract for the execution buffer."""

    def start_execution(
        self,
        integrated_agent_uuid: Optional[UUID],
        contact_urn: str,
        webhook_payload: Dict[str, Any],
        order_id: Optional[str] = None,
        amount: Optional[Decimal] = None,
        currency: Optional[str] = None,
    ) -> UUID:
        """Create the DB row at ``processing`` and seed Redis state."""
        ...

    def add_trace(
        self,
        execution_uuid: UUID,
        trace_type: str,
        data: Dict[str, Any],
    ) -> bool:
        """Append a trace entry. Returns False on Redis failure."""
        ...

    def update_metadata(
        self,
        execution_uuid: UUID,
        **fields: Any,
    ) -> bool:
        """Update one or more fields on the Redis-backed metadata hash.

        Terminal statuses (``success`` / ``error`` / ``skip``) also bump
        the flush-queue ZSET score so the next flush tick picks the
        execution up immediately.
        """
        ...
