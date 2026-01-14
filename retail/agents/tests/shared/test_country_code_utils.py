import unittest
from unittest.mock import patch

from retail.agents.shared.country_code_utils import (
    extract_region_from_locale,
    get_country_phone_code_from_locale,
    convert_vtex_locale_to_meta_language,
)


class TestExtractRegionFromLocale(unittest.TestCase):
    def test_extract_region_from_pt_br(self):
        self.assertEqual(extract_region_from_locale("pt-BR"), "BR")

    def test_extract_region_from_es_ar(self):
        self.assertEqual(extract_region_from_locale("es-AR"), "AR")

    def test_extract_region_from_en_us(self):
        self.assertEqual(extract_region_from_locale("en-US"), "US")

    def test_extract_region_from_es_mx(self):
        self.assertEqual(extract_region_from_locale("es-MX"), "MX")

    def test_extract_region_empty_string_returns_default(self):
        self.assertEqual(extract_region_from_locale(""), "BR")

    def test_extract_region_none_returns_default(self):
        self.assertEqual(extract_region_from_locale(None), "BR")

    def test_extract_region_no_hyphen_returns_default(self):
        self.assertEqual(extract_region_from_locale("ptBR"), "BR")

    def test_extract_region_lowercase_returns_uppercase(self):
        self.assertEqual(extract_region_from_locale("pt-br"), "BR")


class TestGetCountryPhoneCodeFromLocale(unittest.TestCase):
    def test_get_country_phone_code_brazil(self):
        self.assertEqual(get_country_phone_code_from_locale("pt-BR"), "55")

    def test_get_country_phone_code_argentina(self):
        self.assertEqual(get_country_phone_code_from_locale("es-AR"), "54")

    def test_get_country_phone_code_usa(self):
        self.assertEqual(get_country_phone_code_from_locale("en-US"), "1")

    def test_get_country_phone_code_mexico(self):
        self.assertEqual(get_country_phone_code_from_locale("es-MX"), "52")

    def test_get_country_phone_code_chile(self):
        self.assertEqual(get_country_phone_code_from_locale("es-CL"), "56")

    def test_get_country_phone_code_colombia(self):
        self.assertEqual(get_country_phone_code_from_locale("es-CO"), "57")

    def test_get_country_phone_code_peru(self):
        self.assertEqual(get_country_phone_code_from_locale("es-PE"), "51")

    def test_get_country_phone_code_empty_returns_default(self):
        self.assertEqual(get_country_phone_code_from_locale(""), "55")

    def test_get_country_phone_code_none_returns_default(self):
        self.assertEqual(get_country_phone_code_from_locale(None), "55")

    def test_get_country_phone_code_invalid_locale_returns_default(self):
        self.assertEqual(get_country_phone_code_from_locale("invalid"), "55")

    @patch(
        "retail.agents.shared.country_code_utils.phonenumbers.country_code_for_region"
    )
    def test_get_country_phone_code_exception_returns_default(self, mock_country_code):
        mock_country_code.side_effect = Exception("Test error")
        self.assertEqual(get_country_phone_code_from_locale("pt-BR"), "55")


class TestConvertVtexLocaleToMetaLanguage(unittest.TestCase):
    """Tests for VTEX locale to Meta language conversion."""

    def test_convert_pt_BR(self):
        """pt-BR should convert to pt_BR."""
        self.assertEqual(convert_vtex_locale_to_meta_language("pt-BR"), "pt_BR")

    def test_convert_es_AR(self):
        """es-AR should convert to es_AR."""
        self.assertEqual(convert_vtex_locale_to_meta_language("es-AR"), "es_AR")

    def test_convert_es_MX(self):
        """es-MX should convert to es_MX."""
        self.assertEqual(convert_vtex_locale_to_meta_language("es-MX"), "es_MX")

    def test_convert_es_CL(self):
        """es-CL should convert to es_CL."""
        self.assertEqual(convert_vtex_locale_to_meta_language("es-CL"), "es_CL")

    def test_convert_es_CO(self):
        """es-CO should convert to es_CO."""
        self.assertEqual(convert_vtex_locale_to_meta_language("es-CO"), "es_CO")

    def test_convert_es_PE(self):
        """es-PE should convert to es_PE."""
        self.assertEqual(convert_vtex_locale_to_meta_language("es-PE"), "es_PE")

    def test_convert_en_US(self):
        """en-US should convert to en_US."""
        self.assertEqual(convert_vtex_locale_to_meta_language("en-US"), "en_US")

    def test_convert_en_GB(self):
        """en-GB should convert to en_GB."""
        self.assertEqual(convert_vtex_locale_to_meta_language("en-GB"), "en_GB")

    def test_convert_simple_code_no_change(self):
        """Simple codes without hyphen should remain unchanged."""
        self.assertEqual(convert_vtex_locale_to_meta_language("ro"), "ro")
        self.assertEqual(convert_vtex_locale_to_meta_language("ru"), "ru")
        self.assertEqual(convert_vtex_locale_to_meta_language("de"), "de")

    def test_convert_empty_returns_default(self):
        """Empty string should return default pt_BR."""
        self.assertEqual(convert_vtex_locale_to_meta_language(""), "pt_BR")

    def test_convert_none_returns_default(self):
        """None should return default pt_BR."""
        self.assertEqual(convert_vtex_locale_to_meta_language(None), "pt_BR")


class TestVtexToMetaIntegration(unittest.TestCase):
    """Integration tests validating both country_phone_code and meta_language conversion."""

    def test_brazil_pt_BR(self):
        """Brazil: pt-BR should give phone code 55 and language pt_BR."""
        locale = "pt-BR"
        self.assertEqual(get_country_phone_code_from_locale(locale), "55")
        self.assertEqual(convert_vtex_locale_to_meta_language(locale), "pt_BR")

    def test_argentina_es_AR(self):
        """Argentina: es-AR should give phone code 54 and language es_AR."""
        locale = "es-AR"
        self.assertEqual(get_country_phone_code_from_locale(locale), "54")
        self.assertEqual(convert_vtex_locale_to_meta_language(locale), "es_AR")

    def test_mexico_es_MX(self):
        """Mexico: es-MX should give phone code 52 and language es_MX."""
        locale = "es-MX"
        self.assertEqual(get_country_phone_code_from_locale(locale), "52")
        self.assertEqual(convert_vtex_locale_to_meta_language(locale), "es_MX")

    def test_usa_en_US(self):
        """USA: en-US should give phone code 1 and language en_US."""
        locale = "en-US"
        self.assertEqual(get_country_phone_code_from_locale(locale), "1")
        self.assertEqual(convert_vtex_locale_to_meta_language(locale), "en_US")

    def test_chile_es_CL(self):
        """Chile: es-CL should give phone code 56 and language es_CL."""
        locale = "es-CL"
        self.assertEqual(get_country_phone_code_from_locale(locale), "56")
        self.assertEqual(convert_vtex_locale_to_meta_language(locale), "es_CL")

    def test_colombia_es_CO(self):
        """Colombia: es-CO should give phone code 57 and language es_CO."""
        locale = "es-CO"
        self.assertEqual(get_country_phone_code_from_locale(locale), "57")
        self.assertEqual(convert_vtex_locale_to_meta_language(locale), "es_CO")

    def test_peru_es_PE(self):
        """Peru: es-PE should give phone code 51 and language es_PE."""
        locale = "es-PE"
        self.assertEqual(get_country_phone_code_from_locale(locale), "51")
        self.assertEqual(convert_vtex_locale_to_meta_language(locale), "es_PE")
