import uuid

from unittest.mock import MagicMock

from django.test import TestCase

from retail.agents.domains.agent_integration.usecases.fetch_country_phone_code import (
    FetchCountryPhoneCodeUseCase,
)
from retail.projects.models import Project


class TestFetchCountryPhoneCodeUseCase(TestCase):
    def setUp(self):
        self.project = Project.objects.create(
            uuid=uuid.uuid4(),
            name="Test Project",
            vtex_account="teststore",
        )
        self.mock_vtex_io_service = MagicMock()
        self.use_case = FetchCountryPhoneCodeUseCase(
            vtex_io_service=self.mock_vtex_io_service
        )

    def test_execute_success_with_dict_response(self):
        self.mock_vtex_io_service.proxy_vtex.return_value = {
            "slug": "teststore",
            "defaultLocale": "pt-BR",
            "defaultCurrency": "BRL",
        }

        result = self.use_case.execute(self.project)

        self.assertEqual(result, "+55")
        self.mock_vtex_io_service.proxy_vtex.assert_called_once_with(
            account_domain="teststore.myvtex.com",
            project_uuid=str(self.project.uuid),
            method="GET",
            path="/api/tenant/tenants?q=teststore",
        )

    def test_execute_success_with_list_response(self):
        self.mock_vtex_io_service.proxy_vtex.return_value = [
            {
                "slug": "teststore",
                "defaultLocale": "es-AR",
                "defaultCurrency": "ARS",
            }
        ]

        result = self.use_case.execute(self.project)

        self.assertEqual(result, "+54")

    def test_execute_success_with_us_locale(self):
        self.mock_vtex_io_service.proxy_vtex.return_value = {
            "slug": "usstore",
            "defaultLocale": "en-US",
            "defaultCurrency": "USD",
        }

        result = self.use_case.execute(self.project)

        self.assertEqual(result, "+1")

    def test_execute_no_vtex_account_returns_none(self):
        project_without_vtex = Project.objects.create(
            uuid=uuid.uuid4(),
            name="No VTEX Project",
            vtex_account=None,
        )

        result = self.use_case.execute(project_without_vtex)

        self.assertIsNone(result)
        self.mock_vtex_io_service.proxy_vtex.assert_not_called()

    def test_execute_empty_response_returns_none(self):
        self.mock_vtex_io_service.proxy_vtex.return_value = None

        result = self.use_case.execute(self.project)

        self.assertIsNone(result)

    def test_execute_empty_list_response_returns_none(self):
        self.mock_vtex_io_service.proxy_vtex.return_value = []

        result = self.use_case.execute(self.project)

        self.assertIsNone(result)

    def test_execute_no_locale_in_response_returns_none(self):
        self.mock_vtex_io_service.proxy_vtex.return_value = {
            "slug": "teststore",
        }

        result = self.use_case.execute(self.project)

        # Should return default since locale is empty string
        self.assertIsNone(result)

    def test_execute_exception_returns_none(self):
        self.mock_vtex_io_service.proxy_vtex.side_effect = Exception("API Error")

        result = self.use_case.execute(self.project)

        self.assertIsNone(result)

    def test_extract_locale_with_dict(self):
        response = {"defaultLocale": "pt-BR"}
        result = self.use_case._extract_locale(response)
        self.assertEqual(result, "pt-BR")

    def test_extract_locale_with_list(self):
        response = [{"defaultLocale": "es-MX"}]
        result = self.use_case._extract_locale(response)
        self.assertEqual(result, "es-MX")

    def test_extract_locale_empty_response(self):
        result = self.use_case._extract_locale(None)
        self.assertIsNone(result)

    def test_extract_locale_empty_list(self):
        result = self.use_case._extract_locale([])
        self.assertIsNone(result)


class TestFetchCountryPhoneCodeUseCaseDefaultService(TestCase):
    def test_init_creates_default_service(self):
        use_case = FetchCountryPhoneCodeUseCase()
        self.assertIsNotNone(use_case.vtex_io_service)
