from unittest.mock import MagicMock

from django.test import TestCase

from retail.vtex.usecases.create_project_user import (
    CreateProjectUserDTO,
    CreateProjectUserUseCase,
)


class TestCreateProjectUserUseCase(TestCase):
    def setUp(self):
        self.connect_service = MagicMock()
        self.vtex_io_service = MagicMock()
        self.usecase = CreateProjectUserUseCase(
            connect_service=self.connect_service,
            vtex_io_service=self.vtex_io_service,
        )
        self.dto = CreateProjectUserDTO(
            vtex_account="mystore",
            user_email="user@example.com",
        )

    def _mock_tenant_response(self, locale):
        self.vtex_io_service.proxy_vtex.return_value = [{"defaultLocale": locale}]

    def test_execute_fetches_locale_and_creates_project(self):
        self._mock_tenant_response("pt-BR")
        self.connect_service.create_vtex_project.return_value = {
            "project_uuid": "abc-123",
            "user_uuid": "user-456",
        }

        result = self.usecase.execute(self.dto)

        self.vtex_io_service.proxy_vtex.assert_called_once_with(
            account_domain="mystore.myvtex.com",
            vtex_account="mystore",
            method="GET",
            path="/api/tenant/tenants?q=mystore",
        )
        self.connect_service.create_vtex_project.assert_called_once_with(
            user_email="user@example.com",
            vtex_account="mystore",
            language="pt-br",
        )
        self.assertEqual(result["project_uuid"], "abc-123")

    def test_execute_english_locale(self):
        self._mock_tenant_response("en-US")
        self.connect_service.create_vtex_project.return_value = {"project_uuid": "p1"}

        self.usecase.execute(self.dto)

        self.connect_service.create_vtex_project.assert_called_once_with(
            user_email="user@example.com",
            vtex_account="mystore",
            language="en-us",
        )

    def test_execute_spanish_locale(self):
        self._mock_tenant_response("es-AR")
        self.connect_service.create_vtex_project.return_value = {"project_uuid": "p2"}

        self.usecase.execute(self.dto)

        self.connect_service.create_vtex_project.assert_called_once_with(
            user_email="user@example.com",
            vtex_account="mystore",
            language="es-ar",
        )

    def test_execute_falls_back_when_proxy_fails(self):
        self.vtex_io_service.proxy_vtex.side_effect = Exception("proxy error")
        self.connect_service.create_vtex_project.return_value = {"project_uuid": "p3"}

        self.usecase.execute(self.dto)

        self.connect_service.create_vtex_project.assert_called_once_with(
            user_email="user@example.com",
            vtex_account="mystore",
            language="pt-br",
        )

    def test_execute_falls_back_when_no_locale_in_response(self):
        self.vtex_io_service.proxy_vtex.return_value = [{}]
        self.connect_service.create_vtex_project.return_value = {"project_uuid": "p4"}

        self.usecase.execute(self.dto)

        self.connect_service.create_vtex_project.assert_called_once_with(
            user_email="user@example.com",
            vtex_account="mystore",
            language="pt-br",
        )

    def test_extract_locale_from_list_response(self):
        locale = CreateProjectUserUseCase._extract_locale([{"defaultLocale": "pt-BR"}])
        self.assertEqual(locale, "pt-BR")

    def test_extract_locale_from_dict_response(self):
        locale = CreateProjectUserUseCase._extract_locale({"defaultLocale": "en-US"})
        self.assertEqual(locale, "en-US")

    def test_extract_locale_returns_none_for_empty(self):
        self.assertIsNone(CreateProjectUserUseCase._extract_locale(None))
        self.assertIsNone(CreateProjectUserUseCase._extract_locale([]))
