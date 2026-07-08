from uuid import uuid4

from django.db import Error, IntegrityError, transaction
from django.test import TestCase

from retail.contracts.exceptions import ContractAcceptanceImmutableError
from retail.contracts.models import ContractAcceptance, ContractTemplate
from retail.projects.models import Project


class ContractAcceptanceModelTests(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid4(), name="Test Store", vtex_account="teststore"
        )
        self.template = ContractTemplate.objects.create(
            version="v2.1",
            template_name="contract/pdf/v1.html",
        )

    def _create_acceptance(self, **overrides) -> ContractAcceptance:
        defaults = dict(
            user_id=uuid4(),
            email_at_acceptance="user@example.com",
            company_name="Test Store",
            user_name="Carlos Eduardo Ferreira",
            project=self.project,
            vtex_account="teststore",
            accepted_at_local_offset="-03:00",
            contract_template=self.template,
            contract_version=self.template.version,
            contract_document_key="contratos/teststore/x.pdf",
            plan_snapshot={"plan": "Growth"},
            ip_address="127.0.0.1",
            user_agent="Mozilla/5.0",
            session_id="session-123",
            acceptance_method=ContractAcceptance.ACCEPTANCE_METHOD_CHECKBOX,
            checkbox_label_text="I accept the terms.",
        )
        defaults.update(overrides)
        return ContractAcceptance.objects.create(**defaults)

    def test_save_on_existing_row_raises(self):
        acceptance = self._create_acceptance()

        acceptance.session_id = "tampered"
        with self.assertRaises(ContractAcceptanceImmutableError):
            acceptance.save()

    def test_delete_raises(self):
        acceptance = self._create_acceptance()

        with self.assertRaises(ContractAcceptanceImmutableError):
            acceptance.delete()

    def test_db_trigger_blocks_update(self):
        acceptance = self._create_acceptance()

        with self.assertRaises(Error):
            with transaction.atomic():
                ContractAcceptance.objects.filter(pk=acceptance.pk).update(
                    session_id="tampered"
                )

    def test_db_trigger_blocks_delete(self):
        acceptance = self._create_acceptance()

        with self.assertRaises(Error):
            with transaction.atomic():
                ContractAcceptance.objects.filter(pk=acceptance.pk).delete()

    def test_invalid_local_offset_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_acceptance(accepted_at_local_offset="-3:00")

    def test_invalid_acceptance_method_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_acceptance(acceptance_method="signature")

    def test_lowercase_geo_country_rejected(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._create_acceptance(geo_country="br")

    def test_uppercase_geo_country_accepted(self):
        acceptance = self._create_acceptance(geo_country="BR")

        self.assertEqual(acceptance.geo_country, "BR")

    def test_contract_template_str(self):
        self.assertEqual(str(self.template), "ContractTemplate v2.1")

    def test_contract_acceptance_str(self):
        acceptance = self._create_acceptance()

        self.assertEqual(
            str(acceptance), f"ContractAcceptance {acceptance.uuid} (teststore)"
        )
