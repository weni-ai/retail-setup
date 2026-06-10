"""Tests for ``ExportAgentLogsUseCase``.

The export must apply the same filter semantics as the list endpoint
so the file the user downloads matches the screen they were looking
at, write a CSV with a stable column order, and upload it to S3 with
a tenant + agent-scoped key.
"""

import csv
import io
from datetime import date, datetime, timezone as dt_timezone
from decimal import Decimal
from unittest.mock import patch
from uuid import uuid4

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    CSV_HEADER,
    ExportAgentLogsDTO,
    ExportAgentLogsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project


class _FakeS3Service:
    """Minimal stand-in that captures streamed upload calls."""

    def __init__(self):
        self.upload_calls = []

    def upload_fileobj(self, fileobj, key, content_type="application/octet-stream"):
        self.upload_calls.append((key, fileobj.read(), content_type))
        return key

    def get_object(self, key):  # pragma: no cover - unused in tests
        return None


def _make_execution(integrated_agent, **overrides) -> AgentExecution:
    fields = dict(
        uuid=uuid4(),
        contact_urn="whatsapp:+5511999998888",
        status=AgentExecutionStatus.SUCCESS,
        integrated_agent=integrated_agent,
        order_id="ORD-1",
        amount=Decimal("100.00"),
        currency="BRL",
    )
    fields.update(overrides)
    return AgentExecution.objects.create(**fields)


class ExportAgentLogsUseCaseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.fake_s3 = _FakeS3Service()
        self.use_case = ExportAgentLogsUseCase(s3_service=self.fake_s3)

        self.project = Project.objects.create(name="Project A", uuid=uuid4())
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

    def _filter(self, **overrides) -> ExportAgentLogsDTO:
        defaults = dict(
            agent_uuid=self.integrated_agent.uuid,
            project_uuid=self.project.uuid,
        )
        defaults.update(overrides)
        return ExportAgentLogsDTO(**defaults)

    def _csv_rows(self, content_bytes: bytes):
        reader = csv.reader(io.StringIO(content_bytes.decode("utf-8")))
        return list(reader)

    def test_writes_header_row_first(self):
        _make_execution(self.integrated_agent)

        self.use_case.execute(self._filter())

        self.assertEqual(len(self.fake_s3.upload_calls), 1)
        _, content, content_type = self.fake_s3.upload_calls[0]
        self.assertEqual(content_type, "text/csv")
        rows = self._csv_rows(content)
        self.assertEqual(rows[0], CSV_HEADER)

    def test_each_row_uses_log_status_and_default_currency(self):
        _make_execution(
            self.integrated_agent,
            status=AgentExecutionStatus.SKIP,
            currency=None,
            amount=None,
        )

        self.use_case.execute(self._filter())

        _, content, _ = self.fake_s3.upload_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(len(rows), 2)
        data_row = dict(zip(rows[0], rows[1]))
        self.assertEqual(data_row["status"], "skipped")
        self.assertEqual(data_row["currency"], "BRL")
        self.assertEqual(data_row["amount"], "0.00")

    def test_key_is_scoped_by_project_and_agent(self):
        _make_execution(self.integrated_agent)

        self.use_case.execute(self._filter())

        key, _, _ = self.fake_s3.upload_calls[0]
        prefix = f"exports/agent_logs/{self.project.uuid}/{self.integrated_agent.uuid}/"
        self.assertTrue(
            key.startswith(prefix),
            f"key {key!r} should start with {prefix!r}",
        )
        self.assertTrue(key.endswith(".csv"))

    def test_returns_uploaded_key(self):
        _make_execution(self.integrated_agent)
        _make_execution(self.integrated_agent)

        key = self.use_case.execute(self._filter())

        uploaded_key, _, _ = self.fake_s3.upload_calls[0]
        self.assertEqual(key, uploaded_key)

    def test_filter_smoke_check_search_pipes_through(self):
        """One smoke-check that ``ExportAgentLogsDTO`` is forwarded to
        the underlying queryset; full filter-semantics coverage lives in
        ``test_list_agent_logs_usecase.py`` to avoid duplicating the
        date / template / multi-status / courier-join matrix.
        """
        _make_execution(self.integrated_agent, contact_urn="whatsapp:+5511777777777")
        _make_execution(self.integrated_agent, contact_urn="whatsapp:+5511222222222")

        self.use_case.execute(self._filter(search="777777"))

        _, content, _ = self.fake_s3.upload_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(len(rows), 2, "header + one matching execution")

    def test_date_range_filter_pipes_through(self):
        inside = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=inside.uuid).update(
            created_on=datetime(2026, 5, 2, 8, 0, tzinfo=dt_timezone.utc)
        )
        outside = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=outside.uuid).update(
            created_on=datetime(2026, 5, 9, 8, 0, tzinfo=dt_timezone.utc)
        )

        self.use_case.execute(
            self._filter(start_date=date(2026, 5, 1), end_date=date(2026, 5, 5))
        )

        _, content, _ = self.fake_s3.upload_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(len(rows), 2, "header + one in-range execution")
        data_row = dict(zip(rows[0], rows[1]))
        self.assertEqual(data_row["uuid"], str(inside.uuid))


class ExportAgentLogsBucketResolutionTests(TestCase):
    """The constructor resolves the bucket from ``AGENT_LOGS_EXPORT_BUCKET``
    or ``AWS_STORAGE_BUCKET_NAME`` and raises ``ImproperlyConfigured`` when
    neither is set, so misconfigured deploys fail loudly instead of
    routing exports to a placeholder bucket.
    """

    @override_settings(AWS_STORAGE_BUCKET_NAME="fallback-bucket")
    def test_falls_back_to_aws_storage_bucket_name(self):
        with patch(
            "retail.agents.domains.agent_execution.usecases."
            "export_agent_logs.S3Service"
        ) as mock_s3_cls:
            ExportAgentLogsUseCase()

        mock_s3_cls.assert_called_once_with(bucket_name="fallback-bucket")

    @override_settings(AGENT_LOGS_EXPORT_BUCKET="explicit-bucket")
    def test_uses_explicit_export_bucket_when_set(self):
        with patch(
            "retail.agents.domains.agent_execution.usecases."
            "export_agent_logs.S3Service"
        ) as mock_s3_cls:
            ExportAgentLogsUseCase()

        mock_s3_cls.assert_called_once_with(bucket_name="explicit-bucket")

    @override_settings(AGENT_LOGS_EXPORT_BUCKET="", AWS_STORAGE_BUCKET_NAME="")
    def test_raises_when_no_bucket_is_configured(self):
        with self.assertRaises(ImproperlyConfigured):
            ExportAgentLogsUseCase()


class ExportAgentLogsKeyTests(TestCase):
    """The key stays deterministic-ish so support can find a fresh export."""

    def test_key_uses_iso_timestamp(self):
        fake_s3 = _FakeS3Service()
        use_case = ExportAgentLogsUseCase(s3_service=fake_s3)

        project = Project.objects.create(name="Project A", uuid=uuid4())
        agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="a",
            description="",
            project=project,
        )
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=agent, project=project
        )

        fixed_now = datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt_timezone.utc)
        with patch(
            "retail.agents.domains.agent_execution.usecases."
            "export_agent_logs.timezone.now",
            return_value=fixed_now,
        ):
            key = use_case.execute(
                ExportAgentLogsDTO(
                    agent_uuid=integrated_agent.uuid,
                    project_uuid=project.uuid,
                )
            )

        self.assertTrue(key.endswith("/20260102T030405Z.csv"))
