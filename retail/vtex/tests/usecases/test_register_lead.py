from unittest.mock import MagicMock
from uuid import uuid4

from django.test import TestCase

from retail.projects.models import Project
from retail.vtex.models import Lead
from retail.vtex.usecases.register_lead import RegisterLeadDTO, RegisterLeadUseCase


class TestRegisterLeadUseCase(TestCase):
    def setUp(self):
        self.vtex_io_service = MagicMock()
        self.usecase = RegisterLeadUseCase(vtex_io_service=self.vtex_io_service)

        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Test Store",
            vtex_account="teststore",
        )
        self.dto = RegisterLeadDTO(
            user_email="user@example.com",
            plan="PRO",
            vtex_account="teststore",
            data={"carts_triggered": 10, "carts_converted": 3},
        )

    def _mock_tenant_response(self, locale):
        self.vtex_io_service.proxy_vtex.return_value = [{"defaultLocale": locale}]

    def test_execute_creates_lead(self):
        self._mock_tenant_response("pt-BR")

        lead = self.usecase.execute(self.dto)

        self.assertEqual(lead.vtex_account, "teststore")
        self.assertEqual(lead.user_email, "user@example.com")
        self.assertEqual(lead.plan, "PRO")
        self.assertEqual(lead.region, "pt-BR")
        self.assertEqual(lead.project, self.project)
        self.assertEqual(lead.data, {"carts_triggered": 10, "carts_converted": 3})

    def test_execute_updates_existing_lead(self):
        self._mock_tenant_response("pt-BR")
        self.usecase.execute(self.dto)

        updated_dto = RegisterLeadDTO(
            user_email="other@example.com",
            plan="ENTERPRISE",
            vtex_account="teststore",
            data={"carts_triggered": 50},
        )
        lead = self.usecase.execute(updated_dto)

        self.assertEqual(Lead.objects.filter(vtex_account="teststore").count(), 1)
        self.assertEqual(lead.plan, "ENTERPRISE")
        self.assertEqual(lead.user_email, "other@example.com")
        self.assertEqual(lead.data, {"carts_triggered": 50})

    def test_execute_fetches_locale_via_proxy(self):
        self._mock_tenant_response("es-MX")

        lead = self.usecase.execute(self.dto)

        self.vtex_io_service.proxy_vtex.assert_called_once_with(
            account_domain="teststore.myvtex.com",
            vtex_account="teststore",
            method="GET",
            path="/api/tenant/tenants?q=teststore",
        )
        self.assertEqual(lead.region, "es-MX")

    def test_execute_region_empty_when_proxy_fails(self):
        self.vtex_io_service.proxy_vtex.side_effect = Exception("timeout")

        lead = self.usecase.execute(self.dto)

        self.assertEqual(lead.region, "")

    def test_execute_region_empty_when_no_locale_in_response(self):
        self.vtex_io_service.proxy_vtex.return_value = [{}]

        lead = self.usecase.execute(self.dto)

        self.assertEqual(lead.region, "")

    def test_execute_raises_when_project_not_found(self):
        dto = RegisterLeadDTO(
            user_email="user@example.com",
            plan="PRO",
            vtex_account="nonexistent",
        )
        self._mock_tenant_response("pt-BR")

        with self.assertRaises(ValueError) as ctx:
            self.usecase.execute(dto)

        self.assertIn("nonexistent", str(ctx.exception))

    def test_extract_locale_from_list_response(self):
        result = RegisterLeadUseCase._extract_locale([{"defaultLocale": "en-US"}])
        self.assertEqual(result, "en-US")

    def test_extract_locale_from_dict_response(self):
        result = RegisterLeadUseCase._extract_locale({"defaultLocale": "es-AR"})
        self.assertEqual(result, "es-AR")

    def test_extract_locale_returns_none_for_empty(self):
        self.assertIsNone(RegisterLeadUseCase._extract_locale(None))
        self.assertIsNone(RegisterLeadUseCase._extract_locale([]))
