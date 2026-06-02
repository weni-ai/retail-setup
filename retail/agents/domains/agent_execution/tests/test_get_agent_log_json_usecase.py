"""Tests for ``GetAgentLogJsonUseCase``.

The use case is the server-side S3 proxy behind
``GET /logs/{log_uuid}/json/``. These tests pin the contract mapping:

- happy path returns the parsed stored payload
- a row outside the agent/project, or no stored payload, or a missing
  object all raise ``NotFound`` (404)
- an unexpected S3 read or a corrupt payload raise ``APIException`` (500)
"""

from unittest.mock import MagicMock
from uuid import uuid4

from botocore.exceptions import ClientError
from django.test import TestCase
from rest_framework.exceptions import APIException, NotFound

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.services.traces_storage import (
    ExecutionTracesStorageService,
)
from retail.agents.domains.agent_execution.tests._fakes import FakeS3Client
from retail.agents.domains.agent_execution.usecases.get_agent_log_json import (
    GetAgentLogJsonDTO,
    GetAgentLogJsonUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project


class GetAgentLogJsonUseCaseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(name="Project A", uuid=uuid4())
        self.other_project = Project.objects.create(name="Other", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent A",
            slug="agent-a",
            description="",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.project
        )
        self.other_integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.other_project
        )

    def _make_execution(self, **overrides) -> AgentExecution:
        defaults = dict(
            uuid=uuid4(),
            contact_urn="whatsapp:+5511999998888",
            status=AgentExecutionStatus.ERROR,
            integrated_agent=self.integrated_agent,
            traces_s3_key="executions/sample/traces.json",
        )
        defaults.update(overrides)
        return AgentExecution.objects.create(**defaults)

    def _use_case_with_payload(self, key: str, content: bytes):
        fake_s3 = FakeS3Client(bucket_name="test-traces")
        fake_s3.objects[key] = content
        storage = ExecutionTracesStorageService(s3_service=fake_s3)
        return GetAgentLogJsonUseCase(traces_storage=storage)

    def _dto(self, log_uuid, **overrides) -> GetAgentLogJsonDTO:
        defaults = dict(
            agent_uuid=self.integrated_agent.uuid,
            project_uuid=self.project.uuid,
            log_uuid=log_uuid,
        )
        defaults.update(overrides)
        return GetAgentLogJsonDTO(**defaults)

    def test_returns_parsed_payload(self):
        key = "executions/found/traces.json"
        execution = self._make_execution(traces_s3_key=key)
        use_case = self._use_case_with_payload(
            key, b'[{"type": "webhook_received", "data": {"a": 1}}]'
        )

        payload = use_case.execute(self._dto(execution.uuid))

        self.assertEqual(payload, [{"type": "webhook_received", "data": {"a": 1}}])

    def test_unknown_log_raises_not_found(self):
        use_case = self._use_case_with_payload("k", b"[]")

        with self.assertRaises(NotFound):
            use_case.execute(self._dto(uuid4()))

    def test_row_from_other_project_raises_not_found(self):
        execution = self._make_execution(
            integrated_agent=self.other_integrated_agent
        )
        use_case = self._use_case_with_payload("k", b"[]")

        with self.assertRaises(NotFound):
            use_case.execute(self._dto(execution.uuid))

    def test_row_without_traces_key_raises_not_found(self):
        execution = self._make_execution(traces_s3_key="")
        use_case = self._use_case_with_payload("k", b"[]")

        with self.assertRaises(NotFound):
            use_case.execute(self._dto(execution.uuid))

    def test_missing_object_raises_not_found(self):
        execution = self._make_execution(traces_s3_key="executions/gone/traces.json")
        # Storage configured with a different key, so the object is absent.
        use_case = self._use_case_with_payload("executions/other/traces.json", b"[]")

        with self.assertRaises(NotFound):
            use_case.execute(self._dto(execution.uuid))

    def test_unexpected_s3_error_raises_api_exception(self):
        execution = self._make_execution()
        storage = MagicMock(spec=ExecutionTracesStorageService)
        storage.read_traces_payload.side_effect = ClientError(
            {"Error": {"Code": "InternalError"}}, "GetObject"
        )
        use_case = GetAgentLogJsonUseCase(traces_storage=storage)

        with self.assertRaises(APIException):
            use_case.execute(self._dto(execution.uuid))

    def test_corrupt_payload_raises_api_exception(self):
        key = "executions/corrupt/traces.json"
        execution = self._make_execution(traces_s3_key=key)
        use_case = self._use_case_with_payload(key, b"<not json>")

        with self.assertRaises(APIException):
            use_case.execute(self._dto(execution.uuid))
