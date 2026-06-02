"""Tests for the pure ``AgentExecution`` → log-row mappers.

These functions are shared by the JSON list serializer and the CSV
export, so any drift between them quickly surfaces as a column /
field mismatch in the API response. Pinning each transformation in
isolation keeps both renderers honest.
"""

from decimal import Decimal
from types import SimpleNamespace

from django.test import SimpleTestCase

from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.row_mapper import (
    DEFAULT_CURRENCY,
    STATUS_TO_SUMMARY,
    format_amount_value,
    format_contact,
    resolve_amount_value,
    resolve_currency,
    resolve_has_json,
    resolve_log_status,
    resolve_summary,
    resolve_template_name,
    resolve_template_uuid,
)
from retail.agents.domains.agent_execution.status_mapping import (
    LOG_STATUS_DELIVERED,
    LOG_STATUS_ERROR,
    LOG_STATUS_PROCESSING,
    LOG_STATUS_READ,
    LOG_STATUS_SENT,
    LOG_STATUS_SKIPPED,
)
from retail.broadcasts.models import BroadcastStatus


def _stub_execution(**kwargs):
    """Build a duck-typed object that satisfies the row mapper's input shape."""
    defaults = dict(
        uuid="00000000-0000-0000-0000-000000000000",
        contact_urn=None,
        order_id=None,
        amount=None,
        currency=None,
        status=AgentExecutionStatus.PROCESSING.value,
        template=None,
        template_id=None,
        traces_s3_key=None,
        created_on=None,
        broadcast_message=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _stub_broadcast_message(status: str) -> SimpleNamespace:
    """Minimal duck-typed BroadcastMessage carrying just ``status``."""
    return SimpleNamespace(status=status)


class FormatContactTests(SimpleTestCase):
    def test_strips_whatsapp_prefix_and_groups_brazilian_mobile(self):
        self.assertEqual(format_contact("whatsapp:+5511999998888"), "+55 11 99999-8888")

    def test_strips_whatsapp_prefix_and_groups_brazilian_landline(self):
        self.assertEqual(format_contact("whatsapp:+551133334444"), "+55 11 3333-4444")

    def test_returns_empty_string_for_none(self):
        self.assertEqual(format_contact(None), "")

    def test_falls_back_to_prefixed_digits_for_unknown_format(self):
        self.assertEqual(format_contact("whatsapp:+12025550100"), "+12025550100")

    def test_keeps_raw_value_when_format_is_completely_unknown(self):
        self.assertEqual(format_contact("not-a-phone"), "not-a-phone")


class TemplateResolutionTests(SimpleTestCase):
    def test_resolves_display_name_from_custom_template(self):
        template = SimpleNamespace(
            display_name="Custom display", name="custom_name", parent=None
        )
        execution = _stub_execution(template=template, template_id="t-1")
        self.assertEqual(resolve_template_name(execution), "Custom display")
        self.assertEqual(resolve_template_uuid(execution), "t-1")

    def test_falls_back_to_parent_display_name(self):
        parent = SimpleNamespace(display_name="Parent display")
        template = SimpleNamespace(
            display_name=None, name="library_name", parent=parent
        )
        execution = _stub_execution(template=template, template_id="t-2")
        self.assertEqual(resolve_template_name(execution), "Parent display")

    def test_falls_back_to_raw_template_name_when_no_display_name(self):
        template = SimpleNamespace(display_name=None, name="raw_name", parent=None)
        execution = _stub_execution(template=template, template_id="t-3")
        self.assertEqual(resolve_template_name(execution), "raw_name")

    def test_returns_none_when_no_template(self):
        execution = _stub_execution(template=None, template_id=None)
        self.assertIsNone(resolve_template_name(execution))
        self.assertIsNone(resolve_template_uuid(execution))


class AmountAndCurrencyResolutionTests(SimpleTestCase):
    def test_returns_decimal_amount_when_present(self):
        execution = _stub_execution(amount=Decimal("199.90"))
        self.assertEqual(resolve_amount_value(execution), Decimal("199.90"))

    def test_falls_back_to_zero_when_amount_missing(self):
        execution = _stub_execution(amount=None)
        self.assertEqual(resolve_amount_value(execution), Decimal("0"))

    def test_returns_currency_when_present(self):
        execution = _stub_execution(currency="USD")
        self.assertEqual(resolve_currency(execution), "USD")

    def test_falls_back_to_default_currency_when_missing(self):
        execution = _stub_execution(currency=None)
        self.assertEqual(resolve_currency(execution), DEFAULT_CURRENCY)

    def test_format_amount_value_keeps_two_decimals(self):
        execution = _stub_execution(amount=Decimal("193.9"))
        self.assertEqual(format_amount_value(execution), "193.90")

    def test_format_amount_value_renders_zero_for_missing_amount(self):
        execution = _stub_execution(amount=None)
        self.assertEqual(format_amount_value(execution), "0.00")

    def test_format_amount_value_rounds_half_up(self):
        execution = _stub_execution(amount=Decimal("10.005"))
        self.assertEqual(format_amount_value(execution), "10.01")


class StatusAndSummaryResolutionTests(SimpleTestCase):
    def test_resolve_log_status_translates_internal_status(self):
        execution = _stub_execution(status=AgentExecutionStatus.SUCCESS.value)
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_SENT)

    def test_resolve_summary_returns_status_specific_text(self):
        for log_status, expected in STATUS_TO_SUMMARY.items():
            self.assertEqual(resolve_summary(log_status), expected)

    def test_resolve_summary_returns_empty_for_unknown_status(self):
        self.assertEqual(resolve_summary("unknown"), "")


class HasJsonResolutionTests(SimpleTestCase):
    """``resolve_has_json`` is True for any terminal row, False while
    the execution is still ``processing``."""

    def test_processing_has_no_payload(self):
        execution = _stub_execution(status=AgentExecutionStatus.PROCESSING.value)
        self.assertFalse(resolve_has_json(execution))

    def test_terminal_statuses_have_a_payload(self):
        for internal in (
            AgentExecutionStatus.SUCCESS.value,
            AgentExecutionStatus.SKIP.value,
            AgentExecutionStatus.ERROR.value,
        ):
            execution = _stub_execution(status=internal)
            self.assertTrue(
                resolve_has_json(execution),
                msg=f"status={internal} should advertise a stored payload",
            )

    def test_courier_driven_statuses_have_a_payload(self):
        for broadcast_status in (
            BroadcastStatus.DELIVERED.value,
            BroadcastStatus.READ.value,
        ):
            execution = _stub_execution(
                status=AgentExecutionStatus.SUCCESS.value,
                broadcast_message=_stub_broadcast_message(broadcast_status),
            )
            self.assertTrue(resolve_has_json(execution))


class BroadcastMessageStatusEnrichmentTests(SimpleTestCase):
    """``resolve_log_status`` for ``success`` rows reads the linked
    ``BroadcastMessage`` so the courier-driven lifecycle bubbles up
    into the agent-logs API. These tests pin the per-state outcome so
    a future re-mapping (e.g. surfacing ``ERRORED`` as a distinct
    log-status value) catches a missing case here."""

    def test_no_broadcast_message_falls_back_to_sent(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message=None,
        )
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_SENT)

    def test_delivered_broadcast_yields_delivered(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message=_stub_broadcast_message(BroadcastStatus.DELIVERED.value),
        )
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_DELIVERED)

    def test_read_broadcast_yields_read(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message=_stub_broadcast_message(BroadcastStatus.READ.value),
        )
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_READ)

    def test_failed_broadcast_yields_error(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message=_stub_broadcast_message(BroadcastStatus.FAILED.value),
        )
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_ERROR)

    def test_errored_broadcast_stays_sent_to_avoid_ui_flapping(self):
        # ERRORED is transient — the courier will retry and may
        # transition to DELIVERED next. Surfacing ``error`` here would
        # cause the row to flap ``error → delivered`` once the retry
        # succeeds; keep it as ``sent`` until the lifecycle settles.
        execution = _stub_execution(
            status=AgentExecutionStatus.SUCCESS.value,
            broadcast_message=_stub_broadcast_message(BroadcastStatus.ERRORED.value),
        )
        self.assertEqual(resolve_log_status(execution), LOG_STATUS_SENT)

    def test_other_lifecycle_states_stay_sent(self):
        for broadcast_status in (
            BroadcastStatus.INITIALIZING.value,
            BroadcastStatus.PENDING.value,
            BroadcastStatus.QUEUED.value,
            BroadcastStatus.SENT.value,
            BroadcastStatus.WIRED.value,
            BroadcastStatus.UNKNOWN.value,
        ):
            execution = _stub_execution(
                status=AgentExecutionStatus.SUCCESS.value,
                broadcast_message=_stub_broadcast_message(broadcast_status),
            )
            self.assertEqual(
                resolve_log_status(execution),
                LOG_STATUS_SENT,
                msg=(
                    f"BroadcastMessage status={broadcast_status} should map "
                    f"to 'sent' for a successful AgentExecution"
                ),
            )

    def test_non_success_internal_status_ignores_broadcast_message(self):
        # The override only applies to ``success`` — other internal
        # statuses must keep their 1:1 mapping regardless of whether a
        # BroadcastMessage row happens to be linked (it shouldn't be,
        # in practice, but we don't want a stale link to silently
        # change the surfaced log-status value).
        broadcast_message = _stub_broadcast_message(BroadcastStatus.DELIVERED.value)
        for internal, expected in (
            (AgentExecutionStatus.PROCESSING.value, LOG_STATUS_PROCESSING),
            (AgentExecutionStatus.SKIP.value, LOG_STATUS_SKIPPED),
            (AgentExecutionStatus.ERROR.value, LOG_STATUS_ERROR),
        ):
            execution = _stub_execution(
                status=internal, broadcast_message=broadcast_message
            )
            self.assertEqual(resolve_log_status(execution), expected)
