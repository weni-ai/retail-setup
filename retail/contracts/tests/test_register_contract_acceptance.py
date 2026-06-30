from datetime import datetime, timezone as dt_timezone
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

TASK_PATH = (
    "retail.contracts.usecases.register_contract_acceptance."
    "task_process_contract_acceptance_document"
)
NOTIFY_TASK_PATH = (
    "retail.contracts.usecases.register_contract_acceptance."
    "task_notify_contract_acceptance"
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
            user_name="Carlos Eduardo Ferreira",
            vtex_account="teststore",
            plan="Growth",
            acceptance_method="checkbox",
            checkbox_label_text="I accept the terms.",
            ip_address="200.10.20.30",
            user_agent="Mozilla/5.0",
            session_id="session-123",
        )
        defaults.update(overrides)
        return RegisterContractAcceptanceDTO(**defaults)

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    def test_execute_persists_record_with_deterministic_key(
        self, mock_task, mock_notify_task
    ):
        acceptance = self.usecase.execute(self._build_dto())

        self.assertEqual(ContractAcceptance.objects.count(), 1)
        self.assertEqual(acceptance.contract_template, self.template)
        self.assertEqual(acceptance.contract_version, "v2.1")
        self.assertEqual(acceptance.plan_snapshot, {"plan": "Growth"})
        self.assertEqual(
            acceptance.contract_document_key,
            f"contratos/teststore/{acceptance.uuid}.pdf",
        )
        mock_task.delay.assert_called_once_with(str(acceptance.uuid))
        mock_notify_task.delay.assert_called_once_with(str(acceptance.uuid))

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    def test_execute_uses_latest_active_template(self, _mock_task, _mock_notify):
        latest = ContractTemplate.objects.create(
            version="v3.0", template_name="contract/pdf/v1.html"
        )

        acceptance = self.usecase.execute(self._build_dto())

        self.assertEqual(acceptance.contract_template, latest)
        self.assertEqual(acceptance.contract_version, "v3.0")

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    def test_execute_freezes_plan_from_dto_in_snapshot(self, _mock_task, _mock_notify):
        acceptance = self.usecase.execute(self._build_dto(plan="Enterprise"))

        self.assertEqual(acceptance.plan_snapshot, {"plan": "Enterprise"})

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    def test_execute_defaults_company_name_to_project_name(
        self, _mock_task, _mock_notify
    ):
        acceptance = self.usecase.execute(self._build_dto())

        self.assertEqual(acceptance.company_name, "Test Store")

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    @patch(
        "retail.contracts.usecases.register_contract_acceptance.timezone.now",
        return_value=datetime(2026, 6, 10, 14, 32, tzinfo=dt_timezone.utc),
    )
    def test_execute_resolves_local_offset_from_acceptance_timezone(
        self, _mock_now, _mock_task, _mock_notify
    ):
        acceptance = self.usecase.execute(self._build_dto())

        self.assertEqual(acceptance.accepted_at_local_offset, "-03:00")

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    def test_execute_persists_explicit_company_name(self, _mock_task, _mock_notify):
        acceptance = self.usecase.execute(
            self._build_dto(company_name="Magazine Luiza S.A.")
        )

        self.assertEqual(acceptance.company_name, "Magazine Luiza S.A.")

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    def test_execute_raises_when_project_not_found(self, mock_task, mock_notify):
        with self.assertRaises(ProjectNotFoundError):
            self.usecase.execute(self._build_dto(vtex_account="missing"))

        mock_task.delay.assert_not_called()
        mock_notify.delay.assert_not_called()

    @patch(NOTIFY_TASK_PATH)
    @patch(TASK_PATH)
    def test_execute_raises_when_no_active_template(self, _mock_task, _mock_notify):
        self.template.is_active = False
        self.template.save(update_fields=["is_active"])

        with self.assertRaises(ContractTemplateNotFoundError):
            self.usecase.execute(self._build_dto())
