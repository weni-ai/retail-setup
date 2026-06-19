"""
Execution context management using Python's contextvars.

This allows execution_uuid to be accessed anywhere in the call stack
without passing it through every method signature.
"""

from contextvars import ContextVar
from typing import Optional
from uuid import UUID


# Context variable to hold the current execution UUID
_current_execution_uuid: ContextVar[Optional[UUID]] = ContextVar(
    "current_execution_uuid", default=None
)


def get_current_execution_uuid() -> Optional[UUID]:
    """Get the current execution UUID from context."""
    return _current_execution_uuid.get()


def set_current_execution_uuid(execution_uuid: Optional[UUID]) -> None:
    """Set the current execution UUID in context."""
    _current_execution_uuid.set(execution_uuid)


def clear_execution_context() -> None:
    """Clear the execution context."""
    _current_execution_uuid.set(None)
