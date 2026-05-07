"""Defensive tests for the agent-logs serializers.

The happy paths are already covered via the view tests; these cases
pin the edge branches that only fire under malformed input or missing
infrastructure:

- ``_CommaSeparatedUUIDsField`` rejects non-string / non-list input
  and list entries that aren't valid UUIDs.
- ``AgentLogRowSerializer.get_json_url`` returns ``None`` across every
  branch that can suppress the presigned URL (no S3 service, missing
  trace key, presign raises, status that doesn't require a URL).
- ``AgentLogRowSerializer.get_sent_at`` handles the ``created_on=None``
  legacy row shape without crashing.
"""

from datetime import datetime, timezone as dt_timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from django.test import SimpleTestCase

from retail.agents.domains.agent_execution.models import AgentExecutionStatus
from retail.agents.domains.agent_execution.serializers import (
    JSON_URL_TTL_SECONDS,
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
        serializer = ExportAgentLogsBodySerializer(data={"template_uuids": []})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data.get("template_uuids"), [])

    def test_valid_list_round_trips_to_uuid_objects(self):
        uuid_a = uuid4()
        serializer = ExportAgentLogsBodySerializer(
            data={"template_uuids": [str(uuid_a)]}
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


class AgentLogRowSerializerJsonUrlTests(SimpleTestCase):
    """Every branch of ``get_json_url``, without hitting real S3.

    The serializer must never bubble an S3 error out to the caller:
    the CSV export and the list response both treat ``json_url`` as an
    optional field, so a broken S3 client falls back to ``null``
    rather than failing the request.
    """

    def test_returns_none_when_status_does_not_require_json_url(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.SUCCESS.value,
            traces_s3_key="executions/sent/traces.json",
        )
        s3_service = MagicMock()
        s3_service.generate_presigned_url.return_value = "https://example.com/presigned"

        serializer = AgentLogRowSerializer(execution, s3_service=s3_service)

        self.assertIsNone(serializer.data["json_url"])
        s3_service.generate_presigned_url.assert_not_called()

    def test_returns_none_when_traces_s3_key_is_missing(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.ERROR.value, traces_s3_key=None
        )
        s3_service = MagicMock()

        serializer = AgentLogRowSerializer(execution, s3_service=s3_service)

        self.assertIsNone(serializer.data["json_url"])
        s3_service.generate_presigned_url.assert_not_called()

    def test_returns_none_when_s3_service_is_none(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.SKIP.value,
            traces_s3_key="executions/skipped/traces.json",
        )

        serializer = AgentLogRowSerializer(execution, s3_service=None)

        self.assertIsNone(serializer.data["json_url"])

    def test_returns_presigned_url_when_s3_service_succeeds(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.SKIP.value,
            traces_s3_key="executions/skipped/traces.json",
        )
        s3_service = MagicMock()
        s3_service.generate_presigned_url.return_value = (
            "https://s3.amazonaws.com/test/signed"
        )

        serializer = AgentLogRowSerializer(execution, s3_service=s3_service)

        self.assertEqual(
            serializer.data["json_url"], "https://s3.amazonaws.com/test/signed"
        )
        s3_service.generate_presigned_url.assert_called_once_with(
            "executions/skipped/traces.json", expiration=JSON_URL_TTL_SECONDS
        )

    def test_returns_none_when_presign_raises(self):
        execution = _stub_execution(
            status=AgentExecutionStatus.ERROR.value,
            traces_s3_key="executions/error/traces.json",
        )
        s3_service = MagicMock()
        s3_service.generate_presigned_url.side_effect = RuntimeError("S3 is down")

        serializer = AgentLogRowSerializer(execution, s3_service=s3_service)

        self.assertIsNone(serializer.data["json_url"])
        s3_service.generate_presigned_url.assert_called_once()


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
