"""Render the contract PDF, email it, and archive it on success.

Runs out-of-band (Celery) after the legal acceptance row is already
persisted. The PDF is emailed to the customer as an attachment through
Connect; only when that dispatch succeeds is the PDF uploaded to S3 for
long-term retention under the key already stored on the acceptance row.
The object lands on the project's standard private bucket under the
``contratos/`` prefix (retained indefinitely; no lifecycle expiration).
"""

import base64
import logging
from typing import Optional

from retail.contracts.models import ContractAcceptance
from retail.contracts.renderers import ContractPdfRendererInterface
from retail.contracts.translations import (
    CONTRACTOR_LEGAL,
    build_contract_email,
    build_electronic_acceptance_notice,
    format_acceptance_datetime,
    get_contract_pdf_labels,
    resolve_language_prefix,
)
from retail.interfaces.services.aws_s3 import S3ServiceInterface
from retail.interfaces.services.connect import ConnectServiceInterface
from retail.services.aws_s3.service import S3Service
from retail.services.connect.service import ConnectService

logger = logging.getLogger(__name__)

PDF_CONTENT_TYPE = "application/pdf"


class ProcessContractAcceptanceDocumentUseCase:
    def __init__(
        self,
        pdf_renderer: ContractPdfRendererInterface,
        connect_service: Optional[ConnectServiceInterface] = None,
        s3_service: Optional[S3ServiceInterface] = None,
    ):
        self.pdf_renderer = pdf_renderer
        self.connect_service = connect_service or ConnectService()
        self.s3_service = s3_service or S3Service()

    def execute(self, acceptance: ContractAcceptance) -> None:
        language = acceptance.project.language or ""

        pdf_bytes = self.pdf_renderer.render(
            acceptance.contract_template.template_name,
            self._build_context(acceptance, language),
        )

        email = build_contract_email(
            language=language,
            plan_name=acceptance.plan_snapshot.get("plan", ""),
            contract_version=acceptance.contract_version,
            accepted_at=acceptance.accepted_at,
        )

        email_result = self.connect_service.send_contract_acceptance_email(
            user_email=acceptance.email_at_acceptance,
            acceptance_id=str(acceptance.uuid),
            subject=email["subject"],
            body_html=email["body_html"],
            file_name=f"contract-{acceptance.contract_version}.pdf",
            file_base64=base64.b64encode(pdf_bytes).decode("ascii"),
        )

        if not email_result or not email_result.get("sent"):
            logger.warning(
                "Contract acceptance email not dispatched; skipping S3 upload: "
                f"acceptance_id={acceptance.uuid}"
            )
            return

        self.s3_service.put_object(
            acceptance.contract_document_key,
            pdf_bytes,
            content_type=PDF_CONTENT_TYPE,
        )
        logger.info(
            "Contract acceptance document delivered and archived: "
            f"acceptance_id={acceptance.uuid} key={acceptance.contract_document_key}"
        )

    @staticmethod
    def _build_context(acceptance: ContractAcceptance, language: str) -> dict:
        labels = get_contract_pdf_labels(language)
        return {
            "labels": labels,
            "lang_code": resolve_language_prefix(language),
            "email": acceptance.email_at_acceptance,
            "company_name": acceptance.company_name,
            "user_name": acceptance.user_name,
            "vtex_account": acceptance.vtex_account,
            "user_id": str(acceptance.user_id),
            "plan": acceptance.plan_snapshot.get("plan"),
            "plan_snapshot": acceptance.plan_snapshot,
            "contract_version": acceptance.contract_version,
            "accepted_at": acceptance.accepted_at,
            "accepted_at_formatted": format_acceptance_datetime(
                acceptance.accepted_at,
                acceptance.accepted_at_local_offset,
                language,
            ),
            "accepted_at_local_offset": acceptance.accepted_at_local_offset,
            "checkbox_label_text": acceptance.checkbox_label_text,
            "ip_address": acceptance.ip_address,
            "acceptance_id": str(acceptance.uuid),
            "contractor": CONTRACTOR_LEGAL,
            "legal_notice": build_electronic_acceptance_notice(
                language=language,
                accepted_at=acceptance.accepted_at,
                local_offset=acceptance.accepted_at_local_offset,
                acceptance_id=str(acceptance.uuid),
            ),
        }
