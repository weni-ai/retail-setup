"""Tests for ``task_export_agent_logs``.

The Celery task is the only entrypoint for the agent-logs CSV export.
It must:

- Parse ``date`` strings ("YYYY-MM-DD") into ``date`` objects.
- Coerce ``agent_uuid`` / ``project_uuid`` strings into ``UUID``.
- Coerce ``template_uuids`` into a tuple of ``UUID``.
- Coerce ``statuses`` into a tuple (preserving the log-status
  values the API accepts).
- Forward every filter to ``ExportAgentLogsUseCase.execute`` exactly.
- Return the presigned URL produced by the use case on success.
- Return ``None`` on any exception so the worker doesn't crash and
  the API surface stays fire-and-forget.
"""

from datetime import date as date_type
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

from django.test import TestCase

from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    ExportAgentLogsDTO,
)


class TaskExportAgentLogsTests(TestCase):
    def setUp(self):
        super().setUp()
        self.agent_uuid = uuid4()
        self.project_uuid = uuid4()

    @patch("retail.agents.tasks.ExportAgentLogsUseCase")
    def test_returns_presigned_url_and_passes_full_filter(self, mock_use_case_cls):
        from retail.agents.tasks import task_export_agent_logs

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = ("some/key.csv", "https://signed/url")
        mock_use_case_cls.return_value = mock_use_case

        template_uuid_a = uuid4()
        template_uuid_b = uuid4()

        result = task_export_agent_logs(
            agent_uuid=str(self.agent_uuid),
            project_uuid=str(self.project_uuid),
            search="alice",
            date="2024-09-26",
            template_uuids=[str(template_uuid_a), str(template_uuid_b)],
            statuses=["sent", "skipped"],
        )

        self.assertEqual(result, "https://signed/url")

        mock_use_case.execute.assert_called_once()
        dto = mock_use_case.execute.call_args.args[0]
        self.assertIsInstance(dto, ExportAgentLogsDTO)
        self.assertEqual(dto.agent_uuid, self.agent_uuid)
        self.assertEqual(dto.project_uuid, self.project_uuid)
        self.assertEqual(dto.search, "alice")
        self.assertEqual(dto.date, date_type(2024, 9, 26))
        # Tuples, not lists — the dataclass declares ``Sequence[UUID]``
        # and the task is expected to coerce on input.
        self.assertEqual(dto.template_uuids, (template_uuid_a, template_uuid_b))
        for tpl in dto.template_uuids:
            self.assertIsInstance(tpl, UUID)
        self.assertEqual(dto.statuses, ("sent", "skipped"))

    @patch("retail.agents.tasks.ExportAgentLogsUseCase")
    def test_optional_filters_default_to_empty_tuples(self, mock_use_case_cls):
        from retail.agents.tasks import task_export_agent_logs

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = ("some/key.csv", "https://signed/url")
        mock_use_case_cls.return_value = mock_use_case

        result = task_export_agent_logs(
            agent_uuid=str(self.agent_uuid),
            project_uuid=str(self.project_uuid),
        )

        self.assertEqual(result, "https://signed/url")

        dto = mock_use_case.execute.call_args.args[0]
        self.assertIsNone(dto.search)
        self.assertIsNone(dto.date)
        self.assertEqual(dto.template_uuids, ())
        self.assertEqual(dto.statuses, ())

    @patch("retail.agents.tasks.ExportAgentLogsUseCase")
    def test_returns_none_when_use_case_raises(self, mock_use_case_cls):
        from retail.agents.tasks import task_export_agent_logs

        mock_use_case = MagicMock()
        mock_use_case.execute.side_effect = RuntimeError("s3 unreachable")
        mock_use_case_cls.return_value = mock_use_case

        with self.assertLogs("retail.agents.tasks", level="ERROR") as log_capture:
            result = task_export_agent_logs(
                agent_uuid=str(self.agent_uuid),
                project_uuid=str(self.project_uuid),
            )

        self.assertIsNone(result)
        # Operators need to know which agent + project failed.
        joined = "\n".join(log_capture.output)
        self.assertIn(str(self.agent_uuid), joined)
        self.assertIn(str(self.project_uuid), joined)

    def test_returns_none_when_uuid_strings_are_malformed(self):
        from retail.agents.tasks import task_export_agent_logs

        # ``UUID("not-a-uuid")`` will raise — the task must swallow it.
        result = task_export_agent_logs(
            agent_uuid="not-a-uuid",
            project_uuid=str(self.project_uuid),
        )

        self.assertIsNone(result)

    def test_returns_none_when_date_string_is_malformed(self):
        from retail.agents.tasks import task_export_agent_logs

        result = task_export_agent_logs(
            agent_uuid=str(self.agent_uuid),
            project_uuid=str(self.project_uuid),
            date="not-a-date",
        )

        self.assertIsNone(result)
