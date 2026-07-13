from unittest.mock import MagicMock

from django.test import TestCase

from retail.services.vtex_io.tenant_locale_service import (
    VtexTenantLocaleService,
    extract_default_locale,
    language_to_geo_country,
    locale_to_geo_country,
)


class TenantLocaleParsingTests(TestCase):
    def test_extract_default_locale_from_list_response(self):
        result = extract_default_locale([{"defaultLocale": "en-US"}])
        self.assertEqual(result, "en-US")

    def test_extract_default_locale_from_dict_response(self):
        result = extract_default_locale({"defaultLocale": "es-AR"})
        self.assertEqual(result, "es-AR")

    def test_extract_default_locale_returns_none_for_empty(self):
        self.assertIsNone(extract_default_locale(None))
        self.assertIsNone(extract_default_locale([]))
        self.assertIsNone(extract_default_locale({}))

    def test_locale_to_geo_country_from_vtex_locale(self):
        self.assertEqual(locale_to_geo_country("en-US"), "US")
        self.assertEqual(locale_to_geo_country("pt-BR"), "BR")

    def test_locale_to_geo_country_returns_none_when_missing_region(self):
        self.assertIsNone(locale_to_geo_country(""))
        self.assertIsNone(locale_to_geo_country("pt"))

    def test_language_to_geo_country_normalizes_underscores(self):
        self.assertEqual(language_to_geo_country("pt-br"), "BR")
        self.assertEqual(language_to_geo_country("en-us"), "US")

    def test_language_to_geo_country_returns_none_when_empty(self):
        self.assertIsNone(language_to_geo_country(None))
        self.assertIsNone(language_to_geo_country(""))


class VtexTenantLocaleServiceTests(TestCase):
    def setUp(self):
        self.vtex_io_service = MagicMock()
        self.service = VtexTenantLocaleService(vtex_io_service=self.vtex_io_service)

    def _mock_tenant_response(self, locale):
        self.vtex_io_service.proxy_vtex.return_value = [{"defaultLocale": locale}]

    def test_fetch_default_locale_returns_locale(self):
        self._mock_tenant_response("es-MX")

        locale = self.service.fetch_default_locale("teststore")

        self.vtex_io_service.proxy_vtex.assert_called_once_with(
            account_domain="teststore.myvtex.com",
            vtex_account="teststore",
            method="GET",
            path="/api/tenant/tenants?q=teststore",
        )
        self.assertEqual(locale, "es-MX")

    def test_fetch_default_locale_returns_empty_when_proxy_fails(self):
        self.vtex_io_service.proxy_vtex.side_effect = Exception("timeout")

        self.assertEqual(self.service.fetch_default_locale("teststore"), "")

    def test_fetch_default_locale_returns_empty_when_no_locale_in_response(self):
        self.vtex_io_service.proxy_vtex.return_value = [{}]

        self.assertEqual(self.service.fetch_default_locale("teststore"), "")

    def test_resolve_geo_country_from_tenant_locale(self):
        self._mock_tenant_response("en-US")

        self.assertEqual(self.service.resolve_geo_country("teststore"), "US")

    def test_resolve_geo_country_falls_back_to_project_language(self):
        self.vtex_io_service.proxy_vtex.side_effect = Exception("timeout")

        geo_country = self.service.resolve_geo_country(
            "teststore",
            fallback_language="pt-br",
        )

        self.assertEqual(geo_country, "BR")

    def test_resolve_geo_country_returns_none_when_unresolvable(self):
        self.vtex_io_service.proxy_vtex.return_value = [{}]

        self.assertIsNone(
            self.service.resolve_geo_country("teststore", fallback_language="")
        )
