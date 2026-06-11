from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from retail.contracts.models import ContractAcceptance, ContractTemplate
from retail.contracts.tasks import task_process_contract_acceptance_document
from retail.projects.models import Project

USE_CASE_PATH = "retail.contracts.tasks.ProcessContractAcceptanceDocumentUseCase"


class TaskProcessContractAcceptanceDocumentTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(), name="Test Store", vtex_account="teststore"
        )
        self.template = ContractTemplate.objects.create(
            version="v2.1", template_name="contract/pdf/v1.html"
        )
        self.acceptance = ContractAcceptance.objects.create(
            user_id=uuid4(),
            email_at_acceptance="user@example.com",
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

    @patch(USE_CASE_PATH)
    def test_delegates_to_use_case(self, mock_uc_cls):
        task_process_contract_acceptance_document(str(self.acceptance.uuid))

        mock_uc_cls.return_value.execute.assert_called_once()
        passed = mock_uc_cls.return_value.execute.call_args[0][0]
        self.assertEqual(passed.uuid, self.acceptance.uuid)

    @patch(USE_CASE_PATH)
    def test_missing_acceptance_is_logged_and_skipped(self, mock_uc_cls):
        task_process_contract_acceptance_document(str(uuid4()))

        mock_uc_cls.return_value.execute.assert_not_called()
