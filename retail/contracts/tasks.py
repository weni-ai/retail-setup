import logging

from celery import shared_task

from retail.contracts.models import ContractAcceptance
from retail.contracts.translations import format_acceptance_datetime
from retail.contracts.usecases.process_contract_acceptance_document import (
    ProcessContractAcceptanceDocumentUseCase,
)
from retail.contracts.weasyprint_renderer import WeasyPrintContractPdfRenderer
from retail.services.notification.contract_acceptance_service import (
    ContractAcceptanceNotificationService,
)

logger = logging.getLogger(__name__)


@shared_task(name="task_process_contract_acceptance_document")
def task_process_contract_acceptance_document(acceptance_uuid: str) -> None:
    """Render, email (as attachment) and archive the contract PDF.

    Best-effort relative to the legal record: the acceptance already
    exists, so a missing row is logged and any downstream failure inside
    the use case must not corrupt the audit trail. Reprocessing is a
    matter of re-running this task with the same UUID.
    """
    try:
        acceptance = ContractAcceptance.objects.select_related(
            "project", "contract_template"
        ).get(uuid=acceptance_uuid)
    except ContractAcceptance.DoesNotExist:
        logger.error(f"ContractAcceptance not found: uuid={acceptance_uuid}")
        return

    use_case = ProcessContractAcceptanceDocumentUseCase(
        pdf_renderer=WeasyPrintContractPdfRenderer(),
    )
    use_case.execute(acceptance)


@shared_task(name="task_notify_contract_acceptance")
def task_notify_contract_acceptance(acceptance_uuid: str) -> None:
    """Send a Slack notification after a contract acceptance is recorded."""
    try:
        acceptance = ContractAcceptance.objects.select_related("project").get(
            uuid=acceptance_uuid
        )
    except ContractAcceptance.DoesNotExist:
        logger.error(f"ContractAcceptance not found: uuid={acceptance_uuid}")
        return

    try:
        language = acceptance.project.language or ""
        accepted_at_formatted = format_acceptance_datetime(
            acceptance.accepted_at,
            acceptance.accepted_at_local_offset,
            language,
        )

        acceptance_data = {
            "acceptance_id": str(acceptance.uuid),
            "company_name": acceptance.company_name,
            "user_name": acceptance.user_name,
            "email": acceptance.email_at_acceptance,
            "vtex_account": acceptance.vtex_account,
            "plan": acceptance.plan_snapshot.get("plan") or "-",
            "contract_version": acceptance.contract_version,
            "accepted_at": accepted_at_formatted,
            "geo_country": acceptance.geo_country or "",
        }

        ContractAcceptanceNotificationService().notify(acceptance_data)

        logger.info(
            "Contract acceptance Slack notification sent for "
            f"acceptance_id={acceptance.uuid} vtex_account={acceptance.vtex_account}"
        )
    except Exception as exc:
        logger.error(
            "Failed to send contract acceptance notification: "
            f"acceptance_uuid={acceptance_uuid} error={exc}",
            exc_info=True,
        )
