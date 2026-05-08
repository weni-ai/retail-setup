"""Translate between the agent-logs status enum and internal state.

The agent-logs API exposes six lowercase status values: ``processing``,
``skipped``, ``error``, ``sent``, ``delivered``, and ``read``. The
internal model still uses the four-value enum that shipped first:
``processing``, ``skip``, ``error``, and ``success`` (see
``AgentExecutionStatus``); that enum intentionally stays unchanged
because existing rows already use those literals and the buffer Hash
stores them.

The two extra log-status values (``delivered`` and ``read``) are
derived from the linked ``broadcasts.BroadcastMessage`` row created
by ``RecordBroadcastSentUseCase`` at dispatch and advanced by the
courier EDA consumers. The mapping that bridges the gap is:

- ``AgentExecution.status='success'`` AND ``BroadcastMessage.status=DELIVERED`` → ``delivered``
- ``AgentExecution.status='success'`` AND ``BroadcastMessage.status=READ`` → ``read``
- ``AgentExecution.status='success'`` AND ``BroadcastMessage.status=FAILED`` → ``error``
  (permanent courier failure, surfaces as ``error`` even though the dispatch itself succeeded)
- ``AgentExecution.status='success'`` for any other ``BroadcastMessage`` state
  (or no row linked) → ``sent``
- ``AgentExecution.status='error' | 'skip' | 'processing'`` → 1:1 log-status value

``ERRORED`` (transient, courier will retry) intentionally stays in the
``sent`` bucket so the UI does not flap from ``error → delivered`` when
the retry succeeds.

The forward path (rendering one row's status) lives in
``row_mapper.resolve_log_status``; this module owns the reverse
path (turning a list of log-status values into a ``Q`` predicate the
list / export queries can apply).
"""

from typing import Dict, Iterable, Optional

from django.db.models import Q

from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.broadcasts.models import BroadcastStatus


LOG_STATUS_PROCESSING = "processing"
LOG_STATUS_SKIPPED = "skipped"
LOG_STATUS_ERROR = "error"
LOG_STATUS_SENT = "sent"
LOG_STATUS_DELIVERED = "delivered"
LOG_STATUS_READ = "read"


LOG_STATUSES: tuple = (
    LOG_STATUS_PROCESSING,
    LOG_STATUS_SKIPPED,
    LOG_STATUS_ERROR,
    LOG_STATUS_SENT,
    LOG_STATUS_DELIVERED,
    LOG_STATUS_READ,
)


INTERNAL_TO_LOG_STATUS: Dict[str, str] = {
    AgentExecutionStatus.PROCESSING.value: LOG_STATUS_PROCESSING,
    AgentExecutionStatus.SKIP.value: LOG_STATUS_SKIPPED,
    AgentExecutionStatus.ERROR.value: LOG_STATUS_ERROR,
    AgentExecutionStatus.SUCCESS.value: LOG_STATUS_SENT,
}


# BroadcastMessage states that override the default ``sent`` mapping
# when the AgentExecution status is ``success``. Kept as a tuple so
# Django's ``__in`` lookup serializes them correctly.
_BROADCAST_TERMINAL_STATUSES_FOR_VIEW: tuple = (
    BroadcastStatus.DELIVERED.value,
    BroadcastStatus.READ.value,
    BroadcastStatus.FAILED.value,
)


def to_log_status(status: str) -> str:
    """Translate an internal status to its baseline log-status value.

    Does **not** account for the linked ``BroadcastMessage`` — callers
    that need the courier-aware status (``delivered`` / ``read`` /
    courier-driven ``error``) should use
    ``row_mapper.resolve_log_status`` instead.

    Unknown values fall back to ``processing`` so a future internal
    status that hasn't been wired up here doesn't make us emit an
    enum value the client doesn't know how to handle.
    """
    return INTERNAL_TO_LOG_STATUS.get(status, LOG_STATUS_PROCESSING)


def build_status_filter(statuses: Iterable[str]) -> Q:
    """Build a ``Q`` predicate that filters ``AgentExecution`` by log statuses.

    Multiple values combine with ``OR`` so a request like
    ``statuses=sent,delivered`` returns rows in either bucket.
    Duplicate inputs are collapsed. Unknown log-status values are
    dropped silently.

    Returns:
        - ``Q()`` (no constraint) when ``statuses`` is empty — the caller
          shouldn't have filtered in the first place but we don't widen
          accidentally.
        - ``Q(pk__in=[])`` (matches nothing — Django short-circuits to
          ``EmptyResultSet``) when ``statuses`` is non-empty but every
          value was unknown. This preserves the previous behaviour of
          ``to_internal_statuses`` returning ``[]`` and the use case
          short-circuiting to an empty result.
        - An ``OR``-combined predicate otherwise. Joined predicates
          traverse ``broadcast_message__status`` for the courier-derived
          buckets (``delivered`` / ``read``) and for the success-with-
          ``FAILED`` half of the ``error`` bucket.
    """
    seen: set = set()
    predicates = []
    requested = False
    for status in statuses:
        requested = True
        if status in seen:
            continue
        seen.add(status)
        predicate = _build_single_predicate(status)
        if predicate is not None:
            predicates.append(predicate)

    if not requested:
        return Q()
    if not predicates:
        return Q(pk__in=[])

    combined = predicates[0]
    for predicate in predicates[1:]:
        combined |= predicate
    return combined


def _build_single_predicate(status: str) -> Optional[Q]:
    """Return the ``Q`` matching one log-status value, or ``None`` if unknown.

    Kept separate from ``build_status_filter`` so the per-status mapping
    is easy to scan and unit-test in isolation. The ``sent`` predicate
    explicitly accepts rows with no linked ``broadcast_message`` so
    legacy / persistence-failed rows still surface in the ``sent``
    bucket instead of falling through the cracks.
    """
    if status == LOG_STATUS_PROCESSING:
        return Q(status=AgentExecutionStatus.PROCESSING.value)
    if status == LOG_STATUS_SKIPPED:
        return Q(status=AgentExecutionStatus.SKIP.value)
    if status == LOG_STATUS_ERROR:
        return Q(status=AgentExecutionStatus.ERROR.value) | Q(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message__status=BroadcastStatus.FAILED.value,
        )
    if status == LOG_STATUS_DELIVERED:
        return Q(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message__status=BroadcastStatus.DELIVERED.value,
        )
    if status == LOG_STATUS_READ:
        return Q(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message__status=BroadcastStatus.READ.value,
        )
    if status == LOG_STATUS_SENT:
        return Q(status=AgentExecutionStatus.SUCCESS.value) & (
            Q(broadcast_message__isnull=True)
            | ~Q(broadcast_message__status__in=_BROADCAST_TERMINAL_STATUSES_FOR_VIEW)
        )
    return None
