import base64
from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.contracts.models import ContractAcceptance, ContractTemplate
from retail.contracts.usecases.process_contract_acceptance_document import (
    ProcessContractAcceptanceDocumentUseCase,
)
from retail.projects.models import Project


class ProcessContractAcceptanceDocumentUseCaseTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Test Store",
            vtex_account="teststore",
            language="es-MX",
        )
        self.template = ContractTemplate.objects.create(
            version="v2.1", template_name="contract/pdf/v1.html"
        )
        self.acceptance = ContractAcceptance.objects.create(
            user_id=uuid4(),
            email_at_acceptance="user@example.com",
            company_name="Test Store",
            user_name="Carlos Eduardo Ferreira",
            project=self.project,
            vtex_account="teststore",
            accepted_at_local_offset="-03:00",
            contract_template=self.template,
            contract_version="v2.1",
            contract_document_key="contratos/teststore/abc.pdf",
            plan_snapshot={"plan": "Growth"},
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            session_id="session-123",
            acceptance_method="checkbox",
            checkbox_label_text="I accept the terms.",
        )

        self.pdf_renderer = MagicMock()
        self.pdf_renderer.render.return_value = b"%PDF-1.4 fake"
        self.connect_service = MagicMock()
        self.s3_service = MagicMock()
        self.usecase = ProcessContractAcceptanceDocumentUseCase(
            pdf_renderer=self.pdf_renderer,
            connect_service=self.connect_service,
            s3_service=self.s3_service,
        )

    def test_emails_attachment_and_uploads_on_success(self):
        self.connect_service.send_contract_acceptance_email.return_value = {
            "sent": True
        }

        self.usecase.execute(self.acceptance)

        self.pdf_renderer.render.assert_called_once()
        rendered_template, context = self.pdf_renderer.render.call_args[0]
        self.assertEqual(rendered_template, "contract/pdf/v1.html")
        self.assertEqual(context["lang_code"], "es")
        self.assertEqual(context["labels"]["title"], "Contrato de adhesión")
        self.assertIn("acceptance_id", context)
        self.assertIn("legal_notice", context)
        self.assertEqual(context["company_name"], "Test Store")

        expected_date = self.acceptance.accepted_at.strftime("%d/%m/%Y")
        self.connect_service.send_contract_acceptance_email.assert_called_once_with(
            user_email="user@example.com",
            acceptance_id=str(self.acceptance.uuid),
            subject="Tu contrato",
            body_html=(
                "<p>Hola,</p>"
                "<p>Tu aceptación de contrato fue registrada.</p>"
                f"<p>Plan: Growth<br/>Versión: v2.1<br/>Fecha: {expected_date}</p>"
                "<p>El documento aceptado está adjunto a este correo.</p>"
            ),
            file_name="contract-v2.1.pdf",
            file_base64=base64.b64encode(b"%PDF-1.4 fake").decode("ascii"),
        )

        self.s3_service.put_object.assert_called_once_with(
            "contratos/teststore/abc.pdf",
            b"%PDF-1.4 fake",
            content_type="application/pdf",
        )

    def test_skips_upload_when_connect_call_fails(self):
        self.connect_service.send_contract_acceptance_email.return_value = None

        self.usecase.execute(self.acceptance)

        self.s3_service.put_object.assert_not_called()

    def test_skips_upload_when_email_not_sent_flag_false(self):
        self.connect_service.send_contract_acceptance_email.return_value = {
            "sent": False
        }

        self.usecase.execute(self.acceptance)

        self.s3_service.put_object.assert_not_called()
