from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from retail.contracts.exceptions import (
    ContractTemplateNotFoundError,
    ProjectNotFoundError,
)
from retail.contracts.models import ContractAcceptance, ContractTemplate
from retail.contracts.usecases.register_contract_acceptance import (
    RegisterContractAcceptanceDTO,
    RegisterContractAcceptanceUseCase,
)
from retail.projects.models import Project
from retail.vtex.models import Lead

TASK_PATH = (
    "retail.contracts.usecases.register_contract_acceptance."
    "task_process_contract_acceptance_document"
)


class RegisterContractAcceptanceUseCaseTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(), name="Test Store", vtex_account="teststore"
        )
        self.template = ContractTemplate.objects.create(
            version="v2.1", template_name="contract/pdf/v1.html"
        )
        self.usecase = RegisterContractAcceptanceUseCase()

    def _build_dto(self, **overrides) -> RegisterContractAcceptanceDTO:
        defaults = dict(
            user_id=str(uuid4()),
            email_at_acceptance="user@example.com",
            vtex_account="teststore",
            contract_version="v2.1",
            acceptance_method="checkbox",
            checkbox_label_text="I accept the terms.",
            accepted_at_local_offset="-03:00",
            ip_address="200.10.20.30",
            user_agent="Mozilla/5.0",
            session_id="session-123",
            plan_id=str(uuid4()),
        )
        defaults.update(overrides)
        return RegisterContractAcceptanceDTO(**defaults)

    @patch(TASK_PATH)
    def test_execute_persists_record_with_deterministic_key(self, mock_task):
        acceptance = self.usecase.execute(self._build_dto())

        self.assertEqual(ContractAcceptance.objects.count(), 1)
        self.assertEqual(acceptance.contract_template, self.template)
        self.assertEqual(acceptance.contract_version, "v2.1")
        self.assertEqual(
            acceptance.contract_document_key,
            f"contratos/teststore/{acceptance.uuid}.pdf",
        )
        mock_task.delay.assert_called_once_with(str(acceptance.uuid))

    @patch(TASK_PATH)
    def test_execute_uses_latest_active_template_when_version_omitted(self, _mock_task):
        latest = ContractTemplate.objects.create(
            version="v3.0", template_name="contract/pdf/v1.html"
        )

        acceptance = self.usecase.execute(self._build_dto(contract_version=None))

        self.assertEqual(acceptance.contract_template, latest)
        self.assertEqual(acceptance.contract_version, "v3.0")

    @patch(TASK_PATH)
    def test_execute_captures_plan_snapshot_from_lead(self, _mock_task):
        Lead.objects.create(
            user_email="user@example.com",
            vtex_account="teststore",
            project=self.project,
            plan="Growth",
            data={"carts_triggered": 10},
        )

        acceptance = self.usecase.execute(self._build_dto())

        self.assertEqual(
            acceptance.plan_snapshot,
            {"plan": "Growth", "data": {"carts_triggered": 10}},
        )

    @patch(TASK_PATH)
    def test_execute_empty_snapshot_when_no_lead(self, _mock_task):
        acceptance = self.usecase.execute(self._build_dto())

        self.assertEqual(acceptance.plan_snapshot, {})

    @patch(TASK_PATH)
    def test_execute_raises_when_project_not_found(self, mock_task):
        with self.assertRaises(ProjectNotFoundError):
            self.usecase.execute(self._build_dto(vtex_account="missing"))

        mock_task.delay.assert_not_called()

    @patch(TASK_PATH)
    def test_execute_raises_when_template_not_found(self, _mock_task):
        with self.assertRaises(ContractTemplateNotFoundError):
            self.usecase.execute(self._build_dto(contract_version="v9.9"))

    @patch(TASK_PATH)
    def test_execute_ignores_inactive_template(self, _mock_task):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])

        with self.assertRaises(ContractTemplateNotFoundError):
            self.usecase.execute(self._build_dto())
