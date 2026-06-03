"""Tests for the agent-logs status enum translation layer.

The internal model still uses the four-value enum that shipped first;
the agent-logs API exposes a six-value enum, with the two extra
values (``delivered`` and ``read``) derived from the linked
``broadcasts.BroadcastMessage`` row. These tests pin the directional
mappers (``to_log_status`` for the per-row baseline,
``build_status_filter`` for the queryset predicate) so a future
renaming in either direction catches a missing case here.
"""

from django.db.models import Q
from django.test import SimpleTestCase

from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.status_mapping import (
    LOG_STATUS_DELIVERED,
    LOG_STATUS_ERROR,
    LOG_STATUS_PROCESSING,
    LOG_STATUS_READ,
    LOG_STATUS_SENT,
    LOG_STATUS_SKIPPED,
    build_status_filter,
    to_log_status,
)
from retail.broadcasts.models import BroadcastStatus


def _q_to_string(predicate: Q) -> str:
    """Render a ``Q`` predicate as a stable string for structural equality.

    Django doesn't implement ``Q.__eq__`` against arbitrary nested Qs,
    so we compare the deterministic ``repr``-shape that the ORM uses
    internally (children + connector + negated). This is enough to
    catch regressions like ``AND`` vs ``OR`` flipping or missing
    branches without coupling tests to SQL output.
    """
    return repr(predicate)


class BuildStatusFilterTests(SimpleTestCase):
    def test_empty_input_returns_no_constraint(self):
        predicate = build_status_filter([])
        self.assertEqual(_q_to_string(predicate), _q_to_string(Q()))

    def test_unknown_only_input_returns_match_nothing(self):
        predicate = build_status_filter(["totally-bogus", "weird"])
        # ``Q(pk__in=[])`` short-circuits to ``EmptyResultSet`` in Django
        # so the queryset returns 0 rows without hitting the DB.
        self.assertEqual(_q_to_string(predicate), _q_to_string(Q(pk__in=[])))

    def test_processing_predicate(self):
        predicate = build_status_filter([LOG_STATUS_PROCESSING])
        self.assertEqual(
            _q_to_string(predicate),
            _q_to_string(Q(status=AgentExecutionStatus.PROCESSING.value)),
        )

    def test_skipped_predicate(self):
        predicate = build_status_filter([LOG_STATUS_SKIPPED])
        self.assertEqual(
            _q_to_string(predicate),
            _q_to_string(Q(status=AgentExecutionStatus.SKIP.value)),
        )

    def test_delivered_predicate_joins_broadcast_message(self):
        predicate = build_status_filter([LOG_STATUS_DELIVERED])
        self.assertEqual(
            _q_to_string(predicate),
            _q_to_string(
                Q(
                    status=AgentExecutionStatus.SUCCESS.value,
                    broadcast_message__status=BroadcastStatus.DELIVERED.value,
                )
            ),
        )

    def test_read_predicate_joins_broadcast_message(self):
        predicate = build_status_filter([LOG_STATUS_READ])
        self.assertEqual(
            _q_to_string(predicate),
            _q_to_string(
                Q(
                    status=AgentExecutionStatus.SUCCESS.value,
                    broadcast_message__status=BroadcastStatus.READ.value,
                )
            ),
        )

    def test_error_predicate_includes_internal_error_or_courier_failed(self):
        predicate = build_status_filter([LOG_STATUS_ERROR])
        expected = Q(status=AgentExecutionStatus.ERROR.value) | Q(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message__status=BroadcastStatus.FAILED.value,
        )
        self.assertEqual(_q_to_string(predicate), _q_to_string(expected))

    def test_sent_predicate_excludes_terminal_broadcast_states(self):
        predicate = build_status_filter([LOG_STATUS_SENT])
        expected = Q(status=AgentExecutionStatus.SUCCESS.value) & (
            Q(broadcast_message__isnull=True)
            | ~Q(
                broadcast_message__status__in=(
                    BroadcastStatus.DELIVERED.value,
                    BroadcastStatus.READ.value,
                    BroadcastStatus.FAILED.value,
                )
            )
        )
        self.assertEqual(_q_to_string(predicate), _q_to_string(expected))

    def test_multiple_statuses_combine_with_or(self):
        predicate = build_status_filter([LOG_STATUS_DELIVERED, LOG_STATUS_READ])
        expected = Q(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message__status=BroadcastStatus.DELIVERED.value,
        ) | Q(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message__status=BroadcastStatus.READ.value,
        )
        self.assertEqual(_q_to_string(predicate), _q_to_string(expected))

    def test_duplicates_are_collapsed(self):
        once = build_status_filter([LOG_STATUS_PROCESSING])
        twice = build_status_filter([LOG_STATUS_PROCESSING, LOG_STATUS_PROCESSING])
        self.assertEqual(_q_to_string(once), _q_to_string(twice))

    def test_unknown_value_is_dropped_when_mixed_with_valid(self):
        predicate = build_status_filter(["bogus", LOG_STATUS_PROCESSING])
        self.assertEqual(
            _q_to_string(predicate),
            _q_to_string(Q(status=AgentExecutionStatus.PROCESSING.value)),
        )


class ToLogStatusTests(SimpleTestCase):
    """Pure 1:1 mapping for the row-level baseline.

    ``row_mapper.resolve_log_status`` overrides ``sent`` for success
    rows that have a linked ``BroadcastMessage`` — this function only
    handles the internal-only baseline.
    """

    def test_maps_internal_to_log_status(self):
        self.assertEqual(
            to_log_status(AgentExecutionStatus.PROCESSING.value),
            LOG_STATUS_PROCESSING,
        )
        self.assertEqual(
            to_log_status(AgentExecutionStatus.SKIP.value), LOG_STATUS_SKIPPED
        )
        self.assertEqual(
            to_log_status(AgentExecutionStatus.ERROR.value), LOG_STATUS_ERROR
        )
        self.assertEqual(
            to_log_status(AgentExecutionStatus.SUCCESS.value), LOG_STATUS_SENT
        )

    def test_unknown_internal_status_falls_back_to_processing(self):
        self.assertEqual(to_log_status("brand-new-state"), LOG_STATUS_PROCESSING)
