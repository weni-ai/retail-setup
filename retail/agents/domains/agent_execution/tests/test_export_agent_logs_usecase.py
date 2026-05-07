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

from django.test import TestCase, override_settings

from retail.agents.domains.agent_execution.models import (
    AgentExecution,
    AgentExecutionStatus,
)
from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    CSV_HEADER,
    ExportAgentLogsFilter,
    ExportAgentLogsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.templates.models import Template


class _FakeS3Service:
    """Minimal stand-in that captures put / presign calls."""

    def __init__(self):
        self.put_calls = []
        self.presign_calls = []

    def put_object(self, key, content, content_type="application/octet-stream"):
        self.put_calls.append((key, content, content_type))
        return key

    def generate_presigned_url(self, key, expiration=3600):
        self.presign_calls.append((key, expiration))
        return f"https://s3.amazonaws.com/{key}?signature=fake&expiration={expiration}"

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

    def _filter(self, **overrides) -> ExportAgentLogsFilter:
        defaults = dict(
            agent_uuid=self.integrated_agent.uuid,
            project_uuid=self.project.uuid,
        )
        defaults.update(overrides)
        return ExportAgentLogsFilter(**defaults)

    def _csv_rows(self, content_bytes: bytes):
        reader = csv.reader(io.StringIO(content_bytes.decode("utf-8")))
        return list(reader)

    def test_writes_header_row_first(self):
        _make_execution(self.integrated_agent)

        self.use_case.execute(self._filter())

        self.assertEqual(len(self.fake_s3.put_calls), 1)
        _, content, content_type = self.fake_s3.put_calls[0]
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

        _, content, _ = self.fake_s3.put_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(len(rows), 2)
        data_row = dict(zip(rows[0], rows[1]))
        self.assertEqual(data_row["status"], "skipped")
        self.assertEqual(data_row["currency"], "BRL")
        self.assertEqual(data_row["amount"], "0")

    def test_key_is_scoped_by_project_and_agent(self):
        _make_execution(self.integrated_agent)

        self.use_case.execute(self._filter())

        key, _, _ = self.fake_s3.put_calls[0]
        prefix = f"exports/agent_logs/{self.project.uuid}/{self.integrated_agent.uuid}/"
        self.assertTrue(
            key.startswith(prefix),
            f"key {key!r} should start with {prefix!r}",
        )
        self.assertTrue(key.endswith(".csv"))

    def test_returns_presigned_url_and_logs_row_count(self):
        _make_execution(self.integrated_agent)
        _make_execution(self.integrated_agent)

        key, presigned_url = self.use_case.execute(self._filter())

        self.assertEqual(self.fake_s3.presign_calls, [(key, 60 * 60 * 24)])
        self.assertIn("signature=fake", presigned_url)

    def test_filters_apply_same_as_list(self):
        _make_execution(self.integrated_agent, contact_urn="whatsapp:+5511777777777")
        _make_execution(self.integrated_agent, contact_urn="whatsapp:+5511222222222")

        self.use_case.execute(self._filter(search="777777"))

        _, content, _ = self.fake_s3.put_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(len(rows), 2, "header + one matching execution")
        self.assertIn("+55 11 77777-7777", rows[1][CSV_HEADER.index("contact")])

    def test_courier_status_filter_with_no_linked_rows_yields_empty_export(self):
        # ``delivered`` and ``read`` filter through ``broadcast_message``;
        # an execution with no link can never satisfy them, so the
        # CSV should contain only the header.
        _make_execution(self.integrated_agent)

        self.use_case.execute(self._filter(statuses=("delivered", "read")))

        _, content, _ = self.fake_s3.put_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(rows, [CSV_HEADER])

    def test_date_filter_uses_utc_day(self):
        target_day = date(2026, 5, 1)
        in_window = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=in_window.uuid).update(
            created_on=datetime(2026, 5, 1, 12, 0, tzinfo=dt_timezone.utc)
        )
        out_of_window = _make_execution(self.integrated_agent)
        AgentExecution.objects.filter(uuid=out_of_window.uuid).update(
            created_on=datetime(2026, 4, 30, 23, 59, 59, tzinfo=dt_timezone.utc)
        )

        self.use_case.execute(self._filter(date=target_day))

        _, content, _ = self.fake_s3.put_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[1][CSV_HEADER.index("uuid")], str(in_window.uuid))

    def test_template_uuids_filter_mirrors_list_use_case(self):
        """The export shares ``template_uuids`` semantics with the list
        endpoint: rows whose template is in the filter are included;
        rows pointing at a different template are dropped. The screen
        the user exported must match what they were looking at.
        """
        template_a = Template.objects.create(
            uuid=uuid4(),
            name="a",
            integrated_agent=self.integrated_agent,
        )
        template_b = Template.objects.create(
            uuid=uuid4(),
            name="b",
            integrated_agent=self.integrated_agent,
        )
        template_c = Template.objects.create(
            uuid=uuid4(),
            name="c",
            integrated_agent=self.integrated_agent,
        )
        match_a = _make_execution(self.integrated_agent, template=template_a)
        match_b = _make_execution(self.integrated_agent, template=template_b)
        _make_execution(self.integrated_agent, template=template_c)

        self.use_case.execute(
            self._filter(template_uuids=(template_a.uuid, template_b.uuid))
        )

        _, content, _ = self.fake_s3.put_calls[0]
        rows = self._csv_rows(content)
        uuid_col = CSV_HEADER.index("uuid")
        exported_uuids = {row[uuid_col] for row in rows[1:]}
        self.assertEqual(exported_uuids, {str(match_a.uuid), str(match_b.uuid)})

    def test_empty_search_does_not_constrain_results(self):
        """Whitespace-only ``search`` should be treated as no filter;
        the strip-and-check guard exists so an empty query string does
        not ILIKE-match every row twice for no reason.
        """
        kept = _make_execution(self.integrated_agent)

        self.use_case.execute(self._filter(search="   "))

        _, content, _ = self.fake_s3.put_calls[0]
        rows = self._csv_rows(content)
        self.assertEqual(len(rows), 2, "header + the single unfiltered row")
        self.assertEqual(rows[1][CSV_HEADER.index("uuid")], str(kept.uuid))


class ExportAgentLogsBucketFallbackTests(TestCase):
    """The constructor resolves the bucket in two steps:
    ``AGENT_LOGS_EXPORT_BUCKET`` first, falling back to
    ``AWS_STORAGE_BUCKET_NAME``, and finally to ``"test-bucket"`` when
    neither is set. These tests pin the fallback order so a fresh env
    without explicit export-bucket config still boots the use case.
    """

    @override_settings(AWS_STORAGE_BUCKET_NAME="fallback-bucket")
    def test_falls_back_to_aws_storage_bucket_name(self):
        # ``AGENT_LOGS_EXPORT_BUCKET`` is not defined at import time
        # (``getattr(..., None)`` in the use case handles that), so the
        # constructor must pick up ``AWS_STORAGE_BUCKET_NAME`` next.
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
            key, _ = use_case.execute(
                ExportAgentLogsFilter(
                    agent_uuid=integrated_agent.uuid,
                    project_uuid=project.uuid,
                )
            )

        self.assertTrue(key.endswith("/20260102T030405Z.csv"))
