"""Tests for ``SendAgentLogsExportEmailUseCase``.

The use case bridges the loose export filter to the stricter
``send-data-export-email`` contract: it resolves the period (with a
30-day default), collapses the template filter to a single label, and
guarantees a non-empty status list. A missing recipient short-circuits
the whole thing.
"""

from datetime import date, timedelta
from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    ExportAgentLogsDTO,
)
from retail.agents.domains.agent_execution.usecases.send_agent_logs_export_email import (
    SendAgentLogsExportEmailUseCase,
)
from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.interfaces.services.connect import ConnectServiceInterface
from retail.projects.models import Project
from retail.templates.models import Template


class SendAgentLogsExportEmailUseCaseTests(TestCase):
    def setUp(self):
        super().setUp()
        self.connect_service = MagicMock(spec=ConnectServiceInterface)
        self.use_case = SendAgentLogsExportEmailUseCase(
            connect_service=self.connect_service
        )
        self.agent_uuid = uuid4()
        self.project_uuid = uuid4()
        self.file_url = "https://signed/url"

    def _dto(self, **overrides) -> ExportAgentLogsDTO:
        kwargs = {
            "agent_uuid": self.agent_uuid,
            "project_uuid": self.project_uuid,
            "user_email": "user@example.com",
        }
        kwargs.update(overrides)
        return ExportAgentLogsDTO(**kwargs)

    def _sent_payload(self) -> dict:
        return self.connect_service.send_data_export_email.call_args.kwargs

    def test_skips_when_user_email_missing(self):
        self.use_case.execute(self._dto(user_email=None), file_url=self.file_url)

        self.connect_service.send_data_export_email.assert_not_called()

    def test_sends_with_defaults_when_no_filters(self):
        self.use_case.execute(self._dto(), file_url=self.file_url)

        payload = self._sent_payload()
        self.assertEqual(payload["user_email"], "user@example.com")
        self.assertEqual(payload["file_url"], self.file_url)
        self.assertEqual(payload["template"], "all")
        self.assertEqual(payload["status"], ["all"])

        today = timezone.now().date()
        self.assertEqual(payload["end_date"], today.isoformat())
        self.assertEqual(
            payload["start_date"], (today - timedelta(days=30)).isoformat()
        )

    def test_uses_provided_period_and_statuses(self):
        dto = self._dto(
            start_date=date(2026, 4, 1),
            end_date=date(2026, 5, 1),
            statuses=("sent", "delivered"),
        )

        self.use_case.execute(dto, file_url=self.file_url)

        payload = self._sent_payload()
        self.assertEqual(payload["start_date"], "2026-04-01")
        self.assertEqual(payload["end_date"], "2026-05-01")
        self.assertEqual(payload["status"], ["sent", "delivered"])

    def test_single_template_resolves_display_name(self):
        template = Template.objects.create(name="raw_name", display_name="Welcome")

        self.use_case.execute(
            self._dto(template_uuids=(template.uuid,)), file_url=self.file_url
        )

        self.assertEqual(self._sent_payload()["template"], "Welcome")

    def test_multiple_templates_join_display_names(self):
        first = Template.objects.create(name="a", display_name="Alpha")
        second = Template.objects.create(name="b", display_name="Beta")

        self.use_case.execute(
            self._dto(template_uuids=(first.uuid, second.uuid)),
            file_url=self.file_url,
        )

        self.assertEqual(self._sent_payload()["template"], "Alpha, Beta")

    def test_template_falls_back_to_parent_display_name(self):
        project = Project.objects.create(name="P", uuid=uuid4())
        agent = Agent.objects.create(
            uuid=uuid4(), name="A", slug="a", description="", project=project
        )
        parent = PreApprovedTemplate.objects.create(
            agent=agent,
            name="parent",
            display_name="Parent Display",
            start_condition="",
        )
        template = Template.objects.create(name="child", display_name="", parent=parent)

        self.use_case.execute(
            self._dto(template_uuids=(template.uuid,)), file_url=self.file_url
        )

        self.assertEqual(self._sent_payload()["template"], "Parent Display")

    def test_unknown_template_uuid_falls_back_to_all(self):
        self.use_case.execute(
            self._dto(template_uuids=(uuid4(),)), file_url=self.file_url
        )

        self.assertEqual(self._sent_payload()["template"], "all")
