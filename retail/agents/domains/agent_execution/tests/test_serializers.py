"""Defensive tests for the agent-logs serializers.

The happy paths are already covered via the view tests; these cases
pin the edge branches that only fire under malformed input or missing
infrastructure:

- ``_CommaSeparatedUUIDsField`` rejects non-string / non-list input
  and list entries that aren't valid UUIDs.
- ``AgentLogRowSerializer.get_has_json`` derives the flag from the row
  status (terminal -> ``True``, ``processing`` -> ``False``).
- ``AgentLogRowSerializer.get_sent_at`` handles the ``created_on=None``
  legacy row shape without crashing.
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from django.test import SimpleTestCase

from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.serializers import (
    AgentLogRowSerializer,
    ExportAgentLogsBodySerializer,
    ListAgentLogsQuerySerializer,
    _CommaSeparatedUUIDsField,
)


def _stub_execution(**overrides):
    """Duck-typed execution object compatible with the row mapper."""

    defaults = dict(
        uuid=uuid4(),
        contact_urn="whatsapp:+5511999998888",
        order_id="ORD-1",
        amount=None,
        currency=None,
        status=AgentExecutionStatus.SUCCESS.value,
        template=None,
        template_id=None,
        traces_s3_key=None,
        created_on=datetime(2026, 5, 1, 14, 2, 0, tzinfo=dt_timezone.utc),
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class CommaSeparatedUUIDsFieldDirectTests(SimpleTestCase):
    """Exercises ``_CommaSeparatedUUIDsField.to_internal_value`` directly.

    DRF fields need to be bound to a parent serializer for ``fail()``
    to resolve error messages, so every test creates a fresh field via
    a throwaway serializer instance.
    """

    def _field(self) -> _CommaSeparatedUUIDsField:
        serializer = ListAgentLogsQuerySerializer()
        return serializer.fields["template_uuids"]

    def test_none_returns_empty_list(self):
        self.assertEqual(self._field().to_internal_value(None), [])

    def test_empty_string_returns_empty_list(self):
        self.assertEqual(self._field().to_internal_value(""), [])

    def test_empty_list_returns_empty_list(self):
        self.assertEqual(self._field().to_internal_value([]), [])

    def test_string_of_valid_uuids_parses_to_uuid_objects(self):
        uuid_a = uuid4()
        uuid_b = uuid4()
        result = self._field().to_internal_value(f"{uuid_a},{uuid_b}")
        self.assertEqual(result, [uuid_a, uuid_b])

    def test_list_of_valid_uuids_parses_to_uuid_objects(self):
        uuid_a = uuid4()
        uuid_b = uuid4()
        result = self._field().to_internal_value([str(uuid_a), str(uuid_b)])
        self.assertEqual(result, [uuid_a, uuid_b])

    def test_list_strips_whitespace_and_drops_empty_entries(self):
        uuid_a = uuid4()
        result = self._field().to_internal_value([f"  {uuid_a}  ", "   ", ""])
        self.assertEqual(result, [uuid_a])

    def test_tuple_of_valid_uuids_parses_to_uuid_objects(self):
        uuid_a = uuid4()
        result = self._field().to_internal_value((str(uuid_a),))
        self.assertEqual(result, [uuid_a])


class CommaSeparatedUUIDsFieldViaParentSerializerTests(SimpleTestCase):
    """Exercises the field via its parent serializer.

    The ``else`` branch (non-str / non-list input) and the UUID parse
    failure are both routed through ``self.fail("invalid")``. When
    embedded in a serializer that error is collected on the
    ``template_uuids`` key — this is the shape the view actually sees
    when returning the 400 response.
    """

    def test_dict_payload_is_rejected_as_invalid(self):
        serializer = ExportAgentLogsBodySerializer(
            data={"template_uuids": {"foo": "bar"}}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("template_uuids", serializer.errors)

    def test_int_payload_is_rejected_as_invalid(self):
        serializer = ExportAgentLogsBodySerializer(data={"template_uuids": 42})
        self.assertFalse(serializer.is_valid())
        self.assertIn("template_uuids", serializer.errors)

    def test_list_with_non_uuid_entry_is_rejected_as_invalid(self):
        serializer = ExportAgentLogsBodySerializer(
            data={"template_uuids": [str(uuid4()), "not-a-uuid"]}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("template_uuids", serializer.errors)

    def test_comma_separated_string_with_non_uuid_entry_is_rejected(self):
        serializer = ListAgentLogsQuerySerializer(
            data={"template_uuids": f"{uuid4()},not-a-uuid"}
        )
        self.assertFalse(serializer.is_valid())
        self.assertIn("template_uuids", serializer.errors)

    def test_empty_list_is_accepted(self):
        serializer = ExportAgentLogsBodySerializer(
            data={"user_email": "tester@example.com", "template_uuids": []}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get("template_uuids"), [])

    def test_valid_list_round_trips_to_uuid_objects(self):
        uuid_a = uuid4()
        serializer = ExportAgentLogsBodySerializer(
            data={"user_email": "tester@example.com", "template_uuids": [str(uuid_a)]}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        parsed = serializer.validated_data["template_uuids"]
        self.assertEqual(parsed, [uuid_a])
        self.assertIsInstance(parsed[0], UUID)


class CommaSeparatedUUIDsFieldRepresentationTests(SimpleTestCase):
    def test_to_representation_stringifies_each_uuid(self):
        field = _CommaSeparatedUUIDsField()
        uuid_a = uuid4()
        uuid_b = uuid4()
        self.assertEqual(
            field.to_representation([uuid_a, uuid_b]), [str(uuid_a), str(uuid_b)]
        )

    def test_to_representation_handles_none_as_empty_list(self):
        field = _CommaSeparatedUUIDsField()
        self.assertEqual(field.to_representation(None), [])


class CommaSeparatedStatusesFieldViaParentSerializerTests(SimpleTestCase):
    """Exercises ``_CommaSeparatedStatusesField`` via its parent serializer.

    The non-str / non-list branch routes through the shared base's
    ``self.fail("invalid")``; an unknown status value routes through the
    per-entry ``self.fail("invalid_status", value=...)``. Both surface as
    a 400 collected on the ``statuses`` key.
    """

    def test_dict_payload_is_rejected_as_invalid(self):
        serializer = ExportAgentLogsBodySerializer(data={"statuses": {"x": 1}})
        self.assertFalse(serializer.is_valid())
        self.assertIn("statuses", serializer.errors)

    def test_int_payload_is_rejected_as_invalid(self):
        serializer = ExportAgentLogsBodySerializer(data={"statuses": 42})
        self.assertFalse(serializer.is_valid())
        self.assertIn("statuses", serializer.errors)

    def test_unknown_status_value_is_rejected(self):
        serializer = ListAgentLogsQuerySerializer(data={"statuses": "sent,bogus"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("statuses", serializer.errors)

    def test_known_statuses_round_trip(self):
        serializer = ExportAgentLogsBodySerializer(
            data={"user_email": "tester@example.com", "statuses": ["sent", "skipped"]}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["statuses"], ["sent", "skipped"])


class DateRangeValidationTests(SimpleTestCase):
    """``start_date``/``end_date`` must arrive as an ordered pair.

    The contract sends both bounds together (or neither); the serializer
    rejects a lone bound and an inverted range with a 400.
    """

    def test_valid_range_is_accepted(self):
        serializer = ListAgentLogsQuerySerializer(
            data={"start_date": "2026-05-01", "end_date": "2026-05-31"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(str(serializer.validated_data["start_date"]), "2026-05-01")
        self.assertEqual(str(serializer.validated_data["end_date"]), "2026-05-31")

    def test_single_day_range_is_accepted(self):
        serializer = ExportAgentLogsBodySerializer(
            data={
                "user_email": "tester@example.com",
                "start_date": "2026-05-01",
                "end_date": "2026-05-01",
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_both_absent_is_accepted(self):
        serializer = ListAgentLogsQuerySerializer(data={})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertIsNone(serializer.validated_data.get("start_date"))
        self.assertIsNone(serializer.validated_data.get("end_date"))

    def test_only_start_date_is_rejected(self):
        serializer = ListAgentLogsQuerySerializer(data={"start_date": "2026-05-01"})
        self.assertFalse(serializer.is_valid())

    def test_only_end_date_is_rejected(self):
        serializer = ExportAgentLogsBodySerializer(data={"end_date": "2026-05-31"})
        self.assertFalse(serializer.is_valid())

    def test_start_after_end_is_rejected(self):
        serializer = ListAgentLogsQuerySerializer(
            data={"start_date": "2026-05-31", "end_date": "2026-05-01"}
        )
        self.assertFalse(serializer.is_valid())


class ExportUserEmailTests(SimpleTestCase):
    """``user_email`` is the required export destination.

    The request reaches this service through an internal proxy that
    rewrites the authenticated identity, so the recipient can't be
    derived from ``request.user`` — it must arrive in the body and be a
    well-formed address.
    """

    def test_missing_user_email_is_rejected(self):
        serializer = ExportAgentLogsBodySerializer(data={})
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_email", serializer.errors)

    def test_malformed_user_email_is_rejected(self):
        serializer = ExportAgentLogsBodySerializer(data={"user_email": "not-an-email"})
        self.assertFalse(serializer.is_valid())
        self.assertIn("user_email", serializer.errors)

    def test_valid_user_email_round_trips(self):
        serializer = ExportAgentLogsBodySerializer(
            data={"user_email": "recipient@example.com"}
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(
            serializer.validated_data["user_email"], "recipient@example.com"
        )


class AgentLogRowSerializerSentAtTests(SimpleTestCase):
    """``get_sent_at`` is an ISO string or ``None`` — no crash on legacy rows."""

    def test_returns_none_when_created_on_is_none(self):
        execution = _stub_execution(created_on=None)
        serializer = AgentLogRowSerializer(execution)
        self.assertIsNone(serializer.data["sent_at"])

    def test_returns_isoformat_when_created_on_is_set(self):
        created_on = datetime(2026, 5, 1, 14, 2, 0, tzinfo=dt_timezone.utc)
        execution = _stub_execution(created_on=created_on)
        serializer = AgentLogRowSerializer(execution)
        self.assertEqual(serializer.data["sent_at"], created_on.isoformat())


class AgentLogRowSerializerOrderIdTests(SimpleTestCase):
    """``order_id`` is a plain CharField — the value passes through, and a
    legacy ``None`` row renders ``null`` instead of crashing."""

    def test_renders_value_when_present(self):
        execution = _stub_execution(order_id="ORD-1")
        serializer = AgentLogRowSerializer(execution)
        self.assertEqual(serializer.data["order_id"], "ORD-1")

    def test_renders_none_when_absent(self):
        execution = _stub_execution(order_id=None)
        serializer = AgentLogRowSerializer(execution)
        self.assertIsNone(serializer.data["order_id"])


class AgentLogRowSerializerHasJsonTests(SimpleTestCase):
    """``get_has_json`` is derived from the row status, never from S3.

    Every terminal status (``sent`` / ``skipped`` / ``error`` /
    ``delivered`` / ``read``) advertises a stored payload; a
    ``processing`` row is still in flight and reports ``False``.
    """

    def test_true_for_sent(self):
        execution = _stub_execution(status=AgentExecutionStatus.SUCCESS.value)
        serializer = AgentLogRowSerializer(execution)
        self.assertTrue(serializer.data["has_json"])

    def test_true_for_error(self):
        execution = _stub_execution(status=AgentExecutionStatus.ERROR.value)
        serializer = AgentLogRowSerializer(execution)
        self.assertTrue(serializer.data["has_json"])

    def test_true_for_skipped(self):
        execution = _stub_execution(status=AgentExecutionStatus.SKIP.value)
        serializer = AgentLogRowSerializer(execution)
        self.assertTrue(serializer.data["has_json"])

    def test_false_for_processing(self):
        execution = _stub_execution(status=AgentExecutionStatus.PROCESSING.value)
        serializer = AgentLogRowSerializer(execution)
        self.assertFalse(serializer.data["has_json"])


class AgentLogRowSerializerAmountTests(SimpleTestCase):
    """The public ``amount.value`` field is rendered as a 2-decimal string.

    DRF would render a raw ``Decimal`` as a JSON float by default and
    drop the trailing zero (``Decimal("100.00") -> 100.0``), which
    breaks downstream consumers that parse the value as a string. The
    serializer quantizes to two places and emits the value as a string
    so money values round-trip losslessly through JSON.
    """

    def test_preserves_two_decimal_places(self):
        execution = _stub_execution(amount=Decimal("100.00"), currency="BRL")
        serializer = AgentLogRowSerializer(execution)
        self.assertEqual(
            serializer.data["amount"], {"value": "100.00", "currency": "BRL"}
        )

    def test_pads_whole_number_decimals_to_two_places(self):
        execution = _stub_execution(amount=Decimal("5"), currency="USD")
        serializer = AgentLogRowSerializer(execution)
        self.assertEqual(
            serializer.data["amount"], {"value": "5.00", "currency": "USD"}
        )

    def test_legacy_null_amount_falls_back_to_zero_string(self):
        execution = _stub_execution(amount=None, currency=None)
        serializer = AgentLogRowSerializer(execution)
        # Legacy rows with ``amount=None`` surface as ``"0.00"`` (never
        # ``null``) and inherit the default BRL currency so the
        # ``amount`` object is always well-formed.
        self.assertEqual(
            serializer.data["amount"], {"value": "0.00", "currency": "BRL"}
        )

    def test_rounds_half_up_to_two_places(self):
        # Stored Decimals honor the model's ``decimal_places=2``, but
        # pinning the rounding rule here keeps the behaviour defined
        # for any future arithmetic that could introduce third-place
        # digits before the serializer runs.
        execution = _stub_execution(amount=Decimal("10.005"), currency="BRL")
        serializer = AgentLogRowSerializer(execution)
        self.assertEqual(
            serializer.data["amount"], {"value": "10.01", "currency": "BRL"}
        )
