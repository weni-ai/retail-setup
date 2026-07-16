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
import sys
from contextlib import contextmanager
from typing import Any, Callable, Dict, Iterator, List, Optional, Tuple, Type

from celery.exceptions import Retry

from retail.agents.domains.agent_execution.context import (
    clear_execution_context,
    get_current_execution_uuid,
)
from retail.agents.domains.agent_execution.services.logger import (
    ExecutionLoggerService,
)
from retail.observability.sentry import (
    fingerprint_with_vtex_account,
    sentry_error_scope,
)


logger = logging.getLogger(__name__)


@contextmanager
def execution_log_scope(
    *,
    error_data: Optional[Dict[str, Any]] = None,
    error_data_factory: Optional[Callable[[], Dict[str, Any]]] = None,
    reraise: Tuple[Type[BaseException], ...] = (Retry,),
    suppress: Tuple[Type[BaseException], ...] = (Exception,),
    log_prefix: str = "[TASK]",
    sentry_tags: Optional[Dict[str, Any]] = None,
    sentry_fingerprint: Optional[List[str]] = None,
) -> Iterator[ExecutionLoggerService]:
    """Provide an ``ExecutionLoggerService`` and uniform error handling.

    Args:
        error_data: Static dict attached to the error trace if the body
            raises. Use this for context known at scope-open time
            (e.g. ``{"cart_uuid": cart_uuid}``).
        error_data_factory: Lazy alternative to ``error_data`` for
            context that's only known at exception time.
        reraise: Exception classes to re-raise after logging. Defaults
            to ``(Retry,)`` because ``Retry`` subclasses ``Exception``
            and would otherwise be swallowed by ``suppress`` — a bound
            task calling ``self.retry()`` gets its signal propagated
            without having to opt in.
        suppress: Exception classes to swallow after logging. Defaults
            to all ``Exception`` subclasses so a task crash never
            blocks subsequent beat ticks.
        log_prefix: Prefix used in the human-readable error log.
        sentry_tags: Searchable tags (e.g. ``vtex_account``,
            ``project_uuid``) attached to the Sentry event if the body
            raises.
        sentry_fingerprint: Explicit grouping key. Defaults to
            ``[log_prefix, <exception class>]`` so each task groups its
            failures by exception type instead of by rendered message.

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
        _log_terminal_error(
            exec_logger,
            error_data,
            error_data_factory,
            log_prefix,
            sentry_tags=sentry_tags,
            sentry_fingerprint=sentry_fingerprint,
        )
        raise
    except suppress as exc:
        _log_terminal_error(
            exec_logger,
            error_data,
            error_data_factory,
            log_prefix,
            extra_message=str(exc),
            sentry_tags=sentry_tags,
            sentry_fingerprint=sentry_fingerprint,
        )


def _log_terminal_error(
    exec_logger: ExecutionLoggerService,
    error_data: Optional[Dict[str, Any]],
    error_data_factory: Optional[Callable[[], Dict[str, Any]]],
    log_prefix: str,
    extra_message: Optional[str] = None,
    sentry_tags: Optional[Dict[str, Any]] = None,
    sentry_fingerprint: Optional[List[str]] = None,
) -> None:
    """Forward the active task failure to the execution log."""
    exc_type, exc_value, _ = sys.exc_info()
    if exc_value is None:
        return

    exception_name = exc_type.__name__ if exc_type else "Unknown error"
    message = extra_message or str(exc_value) or exception_name

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

    fingerprint = sentry_fingerprint or [log_prefix, exception_name]
    fingerprint = fingerprint_with_vtex_account(fingerprint, sentry_tags)
    with sentry_error_scope(
        fingerprint=fingerprint,
        tags={**(sentry_tags or {}), "error_type": exception_name},
        context={"error": message, "data": payload},
    ):
        logger.error(
            f"{log_prefix} task_failed: error={message} data={payload}",
            exc_info=True,
        )
