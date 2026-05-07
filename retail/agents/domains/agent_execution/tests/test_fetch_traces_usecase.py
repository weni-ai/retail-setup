"""Fetch-traces use case contract.

Replaces the magic ``AgentExecution.traces`` property. The use case
exposes three entry points:

- ``execute(execution)`` — when the caller already has the model,
  short-circuits to ``[]`` if no S3 key is set so we never hit S3 for
  rows that never made it through flush.
- ``execute_for_uuid(uuid)`` — DB lookup, returns ``[]`` when the row
  doesn't exist, never raises.
- ``execute_batch(executions)`` — returns ``Dict[UUID, List[Dict]]``,
  one S3 fetch per execution (no batch read API in S3).
"""

from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.usecases.fetch_traces import (
    FetchTracesUseCase,
)


def _make_execution(traces_s3_key=None) -> AgentExecution:
    return AgentExecution.objects.create(
        uuid=uuid4(),
        contact_urn="whatsapp:+5511999999999",
        status=AgentExecutionStatus.SUCCESS,
        traces_s3_key=traces_s3_key,
    )


class FetchTracesExecuteTests(TestCase):
    def setUp(self):
        super().setUp()
        self.traces_storage = MagicMock(spec=ExecutionTracesStorageService)
        self.use_case = FetchTracesUseCase(traces_storage=self.traces_storage)

    def test_execute_returns_traces_from_s3(self):
        execution = _make_execution(traces_s3_key="executions/x/traces.json")
        self.traces_storage.get_traces.return_value = [{"type": "webhook_received"}]

        result = self.use_case.execute(execution)

        self.assertEqual(result, [{"type": "webhook_received"}])
        self.traces_storage.get_traces.assert_called_once_with(
            execution.uuid, s3_key="executions/x/traces.json"
        )

    def test_execute_short_circuits_when_no_s3_key(self):
        execution = _make_execution(traces_s3_key=None)

        result = self.use_case.execute(execution)

        self.assertEqual(result, [])
        self.traces_storage.get_traces.assert_not_called()

    def test_execute_short_circuits_when_s3_key_blank(self):
        execution = _make_execution(traces_s3_key="")

        result = self.use_case.execute(execution)

        self.assertEqual(result, [])
        self.traces_storage.get_traces.assert_not_called()


class FetchTracesExecuteForUuidTests(TestCase):
    def setUp(self):
        super().setUp()
        self.traces_storage = MagicMock(spec=ExecutionTracesStorageService)
        self.use_case = FetchTracesUseCase(traces_storage=self.traces_storage)

    def test_returns_traces_when_execution_exists(self):
        execution = _make_execution(traces_s3_key="executions/x/traces.json")
        self.traces_storage.get_traces.return_value = [{"type": "skip"}]

        result = self.use_case.execute_for_uuid(execution.uuid)

        self.assertEqual(result, [{"type": "skip"}])

    def test_returns_empty_when_execution_missing(self):
        result = self.use_case.execute_for_uuid(uuid4())
        self.assertEqual(result, [])
        self.traces_storage.get_traces.assert_not_called()

    def test_returns_empty_for_invalid_uuid_string(self):
        """Django raises ``ValidationError`` for malformed UUID strings
        before the query runs; this use case promises "Never raises"
        in its docstring, so the ``ValidationError`` path must collapse
        to the same empty-list return the ``DoesNotExist`` path uses.
        """
        result = self.use_case.execute_for_uuid("not-a-uuid")

        self.assertEqual(result, [])
        self.traces_storage.get_traces.assert_not_called()


class FetchTracesExecuteBatchTests(TestCase):
    def setUp(self):
        super().setUp()
        self.traces_storage = MagicMock(spec=ExecutionTracesStorageService)
        self.use_case = FetchTracesUseCase(traces_storage=self.traces_storage)

    def test_one_get_per_execution_with_s3_key(self):
        with_key_a = _make_execution(traces_s3_key="executions/a/traces.json")
        with_key_b = _make_execution(traces_s3_key="executions/b/traces.json")
        without_key = _make_execution(traces_s3_key=None)

        self.traces_storage.get_traces.side_effect = [
            [{"type": "webhook_received"}],
            [{"type": "skip"}],
        ]

        result = self.use_case.execute_batch([with_key_a, with_key_b, without_key])

        self.assertEqual(result[with_key_a.uuid], [{"type": "webhook_received"}])
        self.assertEqual(result[with_key_b.uuid], [{"type": "skip"}])
        self.assertEqual(result[without_key.uuid], [])
        self.assertEqual(self.traces_storage.get_traces.call_count, 2)

    def test_empty_batch(self):
        self.assertEqual(self.use_case.execute_batch([]), {})
        self.traces_storage.get_traces.assert_not_called()
