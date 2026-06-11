"""Register an immutable, auditable contract acceptance event."""

import logging
from dataclasses import dataclass
from typing import Optional
from uuid import uuid4

from django.utils import timezone

from retail.contracts.exceptions import (
    ContractTemplateNotFoundError,
    ProjectNotFoundError,
)
from retail.contracts.models import ContractAcceptance, ContractTemplate
from retail.contracts.tasks import task_process_contract_acceptance_document
from retail.contracts.usecases.plan_snapshot_resolver import PlanSnapshotResolver
from retail.projects.models import Project

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RegisterContractAcceptanceDTO:
    user_id: str
    email_at_acceptance: str
    vtex_account: str
    acceptance_method: str
    checkbox_label_text: str
    accepted_at_local_offset: str
    ip_address: str
    user_agent: str
    session_id: str
    contract_version: Optional[str] = None
    plan_id: Optional[str] = None
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

    def __init__(self, plan_snapshot_resolver: Optional[PlanSnapshotResolver] = None):
        self.plan_snapshot_resolver = plan_snapshot_resolver or PlanSnapshotResolver()

    def execute(self, dto: RegisterContractAcceptanceDTO) -> ContractAcceptance:
        project = self._get_project(dto.vtex_account)
        template = self._get_template(dto.contract_version)
        plan_snapshot = self.plan_snapshot_resolver.resolve(
            vtex_account=dto.vtex_account, plan_id=dto.plan_id
        )

        acceptance_uuid = uuid4()
        acceptance = ContractAcceptance.objects.create(
            uuid=acceptance_uuid,
            user_id=dto.user_id,
            email_at_acceptance=dto.email_at_acceptance,
            project=project,
            vtex_account=dto.vtex_account,
            accepted_at=timezone.now(),
            accepted_at_local_offset=dto.accepted_at_local_offset,
            contract_template=template,
            contract_version=template.version,
            contract_document_key=self._build_document_key(
                dto.vtex_account, acceptance_uuid
            ),
            plan_id=dto.plan_id,
            plan_snapshot=plan_snapshot,
            ip_address=dto.ip_address,
            user_agent=dto.user_agent,
            session_id=dto.session_id,
            acceptance_method=dto.acceptance_method,
            checkbox_label_text=dto.checkbox_label_text,
            request_id=dto.request_id,
            geo_country=dto.geo_country,
        )

        logger.info(
            f"Contract acceptance registered: acceptance_id={acceptance.uuid} "
            f"vtex_account={dto.vtex_account} contract_version={template.version}"
        )

        task_process_contract_acceptance_document.delay(str(acceptance.uuid))

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
    def _get_template(contract_version: Optional[str]) -> ContractTemplate:
        templates = ContractTemplate.objects.filter(is_active=True)
        if contract_version:
            template = templates.filter(version=contract_version).first()
        else:
            template = templates.order_by("-created_at").first()

        if template is None:
            raise ContractTemplateNotFoundError(
                "Active contract template not found "
                f"(version={contract_version or 'latest'})"
            )
        return template
