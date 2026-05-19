"""Shared boilerplate for Celery tasks that emit execution-log traces.

Most agent-driven tasks share the same shape:

1. Build an ``ExecutionLoggerService``.
2. Run the task body, which may call ``log_webhook_received`` to open
   a new AgentExecution row (its UUID lands in the contextvar).
3. If the body raises, force-finalise the active execution row as
   ``error`` so it doesn't linger in ``processing`` until the ZSET
   deadline expires.

``execution_log_scope`` collapses that into a single context manager.
The task body uses the yielded logger; the context manager handles
the exception path uniformly.
"""

import logging
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, Optional, Type

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    get_current_execution_uuid,
)
from retail.agents.domains.agent_execution.services.logger import (
    ExecutionLoggerService,
)


logger = logging.getLogger(__name__)


@contextmanager
def execution_log_scope(
    *,
    error_data: Optional[Dict[str, Any]] = None,
    error_data_factory: Optional[Callable[[], Dict[str, Any]]] = None,
    reraise: tuple = (),
    suppress: tuple = (Exception,),
    log_prefix: str = "[TASK]",
) -> Iterator[ExecutionLoggerService]:
    """Provide an ``ExecutionLoggerService`` and uniform error handling.

    Args:
        error_data: Static dict attached to the error trace if the body
            raises. Use this for context known at scope-open time
            (e.g. ``{"cart_uuid": cart_uuid}``).
        error_data_factory: Lazy alternative to ``error_data`` for
            context that's only known at exception time.
        reraise: Exception classes to re-raise after logging (e.g.
            celery retry exceptions). Defaults to nothing.
        suppress: Exception classes to swallow after logging. Defaults
            to all ``Exception`` subclasses so a task crash never
            blocks subsequent beat ticks.
        log_prefix: Prefix used in the human-readable error log.

    Yields:
        ``ExecutionLoggerService`` instance the task body should pass
        into use cases / services.
    """
    exec_logger = ExecutionLoggerService()
    # Pre-task signal already clears, but defensive in case a caller
    # invokes the scope outside Celery.
    clear_execution_context()
    try:
        yield exec_logger
    except reraise:
        _log_terminal_error(exec_logger, error_data, error_data_factory, log_prefix)
        raise
    except suppress as exc:
        _log_terminal_error(
            exec_logger,
            error_data,
            error_data_factory,
            log_prefix,
            extra_message=str(exc),
        )


def _log_terminal_error(
    exec_logger: ExecutionLoggerService,
    error_data: Optional[Dict[str, Any]],
    error_data_factory: Optional[Callable[[], Dict[str, Any]]],
    log_prefix: str,
    extra_message: Optional[str] = None,
) -> None:
    """Forward the active task failure to the execution log."""
    import sys

    exc_type: Optional[Type[BaseException]] = sys.exc_info()[0]
    exc_value: Optional[BaseException] = sys.exc_info()[1]
    if exc_value is None:
        return

    message = str(exc_value) or (exc_type.__name__ if exc_type else "Unknown error")

    payload: Dict[str, Any] = {}
    if error_data:
        payload.update(error_data)
    if error_data_factory is not None:
        try:
            payload.update(error_data_factory())
        except Exception:
            logger.exception("error_data_factory raised; continuing with partial data")

    active_uuid = get_current_execution_uuid()
    if active_uuid is not None:
        exec_logger.log_execution_error(
            execution_uuid=active_uuid,
            error_message=message,
            error_data=payload or None,
        )

    logger.error(
        "%s task_failed: error=%s data=%s",
        log_prefix,
        message,
        payload,
        exc_info=True,
    )
