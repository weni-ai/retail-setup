"""Register an immutable, auditable contract acceptance event."""

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from django.utils import timezone

from retail.contracts.acceptance_timezone import resolve_acceptance_local_offset
from retail.contracts.exceptions import (
    ContractTemplateNotFoundError,
    ProjectNotFoundError,
)
from retail.contracts.models import ContractAcceptance, ContractTemplate
from retail.contracts.tasks import (
    task_notify_contract_acceptance,
    task_process_contract_acceptance_document,
)
from retail.projects.models import Project
from retail.services.vtex_io.tenant_locale_service import VtexTenantLocaleService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisterContractAcceptanceDTO:
    user_id: str
    email_at_acceptance: str
    user_name: str
    vtex_account: str
    plan: str
    acceptance_method: str
    checkbox_label_text: str
    ip_address: str
    user_agent: str
    session_id: str
    company_name: Optional[str] = None
    request_id: Optional[str] = None
    geo_country: Optional[str] = None


class RegisterContractAcceptanceUseCase:
    """Persist the legal acceptance record and trigger document delivery.

    The acceptance row is the legally significant artifact, so it is
    written synchronously and unconditionally (the S3 object key is
    deterministic, derived from the acceptance UUID, so it can be stored
    up front). Rendering the PDF, emailing it as an attachment and
    archiving it on S3 happen out-of-band in
    ``task_process_contract_acceptance_document``.
    """

    def __init__(
        self,
        tenant_locale_service: Optional[VtexTenantLocaleService] = None,
    ):
        self.tenant_locale_service = tenant_locale_service or VtexTenantLocaleService()

    def execute(self, dto: RegisterContractAcceptanceDTO) -> ContractAcceptance:
        project = self._get_project(dto.vtex_account)
        template = self._get_active_template()
        geo_country = dto.geo_country or self.tenant_locale_service.resolve_geo_country(
            dto.vtex_account,
            fallback_language=project.language,
        )

        acceptance_uuid = uuid4()
        accepted_at = timezone.now()
        acceptance = ContractAcceptance.objects.create(
            uuid=acceptance_uuid,
            user_id=dto.user_id,
            email_at_acceptance=dto.email_at_acceptance,
            company_name=dto.company_name or project.name,
            user_name=dto.user_name,
            project=project,
            vtex_account=dto.vtex_account,
            accepted_at=accepted_at,
            accepted_at_local_offset=resolve_acceptance_local_offset(accepted_at),
            contract_template=template,
            contract_version=template.version,
            contract_document_key=self._build_document_key(
                dto.vtex_account, acceptance_uuid
            ),
            plan_snapshot={"plan": dto.plan},
            ip_address=dto.ip_address,
            user_agent=dto.user_agent,
            session_id=dto.session_id,
            acceptance_method=dto.acceptance_method,
            checkbox_label_text=dto.checkbox_label_text,
            request_id=dto.request_id,
            geo_country=geo_country,
        )

        logger.info(
            f"Contract acceptance registered: acceptance_id={acceptance.uuid} "
            f"vtex_account={dto.vtex_account} plan={dto.plan} "
            f"contract_version={template.version}"
        )

        task_process_contract_acceptance_document.delay(str(acceptance.uuid))
        task_notify_contract_acceptance.delay(str(acceptance.uuid))

        return acceptance

    @staticmethod
    def _build_document_key(vtex_account: str, acceptance_uuid) -> str:
        return f"contratos/{vtex_account}/{acceptance_uuid}.pdf"

    @staticmethod
    def _get_project(vtex_account: str) -> Project:
        try:
            return Project.objects.get(vtex_account=vtex_account)
        except Project.DoesNotExist:
            raise ProjectNotFoundError(
                f"Project not found for vtex_account: {vtex_account}"
            )

    @staticmethod
    def _get_active_template() -> ContractTemplate:
        template = (
            ContractTemplate.objects.filter(is_active=True)
            .order_by("-created_at")
            .first()
        )
        if template is None:
            raise ContractTemplateNotFoundError("Active contract template not found")
        return template
