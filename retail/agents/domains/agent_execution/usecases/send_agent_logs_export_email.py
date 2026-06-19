"""Use case: notify the export requester that their CSV is ready.

Runs after ``ExportAgentLogsUseCase`` uploads the CSV to S3. It builds
the human-readable summary the email shows (period, template label,
status list), then hands off to Connect's internal
``send-data-export-email`` endpoint through ``ConnectService``.

The email endpoint requires a date range, a single ``template`` label
and a non-empty ``status`` list, while the export filter is looser
(dates optional, multiple templates, multiple statuses). This use case
bridges that gap:

- the period defaults to the last 30 days when the request carried no
  date filter;
- ``template`` is ``all`` when no template was selected, otherwise the
  selected templates' display names joined with ``, ``;
- ``status`` echoes the requested statuses, or ``["all"]`` when none.
"""

import logging
from datetime import timedelta
from typing import List, Optional, Tuple

from django.utils import timezone

from retail.agents.domains.agent_execution.row_mapper import template_display_name
from retail.agents.domains.agent_execution.usecases.export_agent_logs import (
    ExportAgentLogsDTO,
)
from retail.interfaces.services.connect import ConnectServiceInterface
from retail.services.connect.service import ConnectService
from retail.templates.models import Template


logger = logging.getLogger(__name__)


DEFAULT_PERIOD_DAYS = 30
TEMPLATE_LABEL_ALL = "all"
STATUS_ALL = "all"


class SendAgentLogsExportEmailUseCase:
    """Send the "export ready" email for a finished agent-logs export."""

    def __init__(self, connect_service: Optional[ConnectServiceInterface] = None):
        self.connect_service = connect_service or ConnectService()

    def execute(self, dto: ExportAgentLogsDTO, file_url: str) -> None:
        if not dto.user_email:
            logger.warning(
                "[AGENT_LOGS_EXPORT] No recipient email for agent=%s project=%s; "
                "skipping export-ready email",
                dto.agent_uuid,
                dto.project_uuid,
            )
            return

        start_date, end_date = self._resolve_period(dto)

        self.connect_service.send_data_export_email(
            user_email=dto.user_email,
            file_url=file_url,
            start_date=start_date,
            end_date=end_date,
            template=self._resolve_template_label(dto),
            status=self._resolve_statuses(dto),
        )

        logger.info(
            "[AGENT_LOGS_EXPORT] Export-ready email requested for agent=%s "
            "project=%s email=%s",
            dto.agent_uuid,
            dto.project_uuid,
            dto.user_email,
        )

    def _resolve_period(self, dto: ExportAgentLogsDTO) -> Tuple[str, str]:
        if dto.start_date is not None and dto.end_date is not None:
            return dto.start_date.isoformat(), dto.end_date.isoformat()

        today = timezone.now().date()
        start = today - timedelta(days=DEFAULT_PERIOD_DAYS)
        return start.isoformat(), today.isoformat()

    def _resolve_template_label(self, dto: ExportAgentLogsDTO) -> str:
        if not dto.template_uuids:
            return TEMPLATE_LABEL_ALL

        templates = (
            Template.objects.select_related("parent")
            .filter(uuid__in=list(dto.template_uuids))
            .order_by("name")
        )
        names = [name for name in map(template_display_name, templates) if name]
        return ", ".join(names) if names else TEMPLATE_LABEL_ALL

    def _resolve_statuses(self, dto: ExportAgentLogsDTO) -> List[str]:
        return list(dto.statuses) or [STATUS_ALL]
