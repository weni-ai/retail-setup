import logging

from celery import shared_task

from retail.contracts.models import ContractAcceptance
from retail.contracts.usecases.process_contract_acceptance_document import (
    ProcessContractAcceptanceDocumentUseCase,
)
from retail.contracts.weasyprint_renderer import WeasyPrintContractPdfRenderer

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
