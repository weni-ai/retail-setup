"""Publish a product click to the datalake events table."""

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from django.utils import timezone

from retail.metrics.exceptions import ProductMetricPublishError, ProjectNotFoundError
from retail.projects.models import Project
from retail.services.vtex_io.tenant_locale_service import VtexTenantLocaleService
from weni_datalake_sdk.clients.client import send_event_data
from weni_datalake_sdk.paths.events_path import EventPath

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RecordProductMetricEventDTO:
    event_type: str
    user_email: str
    vtex_account: str
    suggested_plan: Optional[str] = None
    project_uuid: Optional[str] = None


class RecordProductMetricEventUseCase:
    """Map a click onto ``EventPath`` and send it.

    The events table requires a project UUID. The token supplies it when
    present; otherwise the active project for the VTEX account is used.
    A failed country lookup omits ``country`` and the event is still sent.
    Nothing is written to Postgres.
    """

    def __init__(
        self,
        send_event: Optional[Callable[..., Any]] = None,
        tenant_locale_service: Optional[VtexTenantLocaleService] = None,
    ):
        self.send_event = send_event or send_event_data
        self.tenant_locale_service = tenant_locale_service or VtexTenantLocaleService()

    def execute(self, dto: RecordProductMetricEventDTO) -> None:
        project_uuid, fallback_language = self._resolve_project(dto)
        country = self.tenant_locale_service.resolve_geo_country(
            dto.vtex_account,
            fallback_language=fallback_language,
        )
        payload = self._event_payload(dto, project_uuid, country)
        self._publish(dto, payload)

    def _resolve_project(
        self, dto: RecordProductMetricEventDTO
    ) -> tuple[str, Optional[str]]:
        if dto.project_uuid:
            return dto.project_uuid, None

        project = self._active_project(dto.vtex_account)
        return str(project.uuid), project.language

    @staticmethod
    def _active_project(vtex_account: str) -> Project:
        try:
            return Project.objects.get(vtex_account=vtex_account)
        except (Project.DoesNotExist, Project.MultipleObjectsReturned) as exc:
            raise ProjectNotFoundError(
                f"Active project not found for vtex_account: {vtex_account}"
            ) from exc

    def _publish(self, dto: RecordProductMetricEventDTO, payload: dict) -> None:
        logger.info(
            f"Publishing product metric event_type={dto.event_type} "
            f"vtex_account={dto.vtex_account} project={payload['project']}"
        )
        try:
            self.send_event(EventPath, payload)
        except Exception as exc:
            logger.error(
                f"Failed to publish product metric event_type={dto.event_type} "
                f"vtex_account={dto.vtex_account}: {exc}",
                exc_info=True,
            )
            raise ProductMetricPublishError(
                "Failed to publish product metric event"
            ) from exc

    @staticmethod
    def _event_payload(
        dto: RecordProductMetricEventDTO,
        project_uuid: str,
        country: Optional[str],
    ) -> dict:
        return {
            "event_name": dto.event_type,
            "key": dto.vtex_account,
            "date": timezone.now().isoformat(),
            "project": project_uuid,
            "value_type": "string",
            "value": dto.suggested_plan or "",
            "contact_urn": "",
            "metadata": RecordProductMetricEventUseCase._metadata(dto, country),
        }

    @staticmethod
    def _metadata(dto: RecordProductMetricEventDTO, country: Optional[str]) -> dict:
        metadata = {
            "user_email": dto.user_email,
            "vtex_account": dto.vtex_account,
        }
        if country:
            metadata["country"] = country
        if dto.suggested_plan:
            metadata["suggested_plan"] = dto.suggested_plan
        return metadata
