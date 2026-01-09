import unittest
from unittest.mock import patch

from retail.agents.shared.country_code_utils import (
    extract_region_from_locale,
    get_phone_code_from_locale,
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


class TestGetPhoneCodeFromLocale(unittest.TestCase):
    def test_get_phone_code_brazil(self):
        self.assertEqual(get_phone_code_from_locale("pt-BR"), "+55")

    def test_get_phone_code_argentina(self):
        self.assertEqual(get_phone_code_from_locale("es-AR"), "+54")

    def test_get_phone_code_usa(self):
        self.assertEqual(get_phone_code_from_locale("en-US"), "+1")

    def test_get_phone_code_mexico(self):
        self.assertEqual(get_phone_code_from_locale("es-MX"), "+52")

    def test_get_phone_code_chile(self):
        self.assertEqual(get_phone_code_from_locale("es-CL"), "+56")

    def test_get_phone_code_colombia(self):
        self.assertEqual(get_phone_code_from_locale("es-CO"), "+57")

    def test_get_phone_code_peru(self):
        self.assertEqual(get_phone_code_from_locale("es-PE"), "+51")

    def test_get_phone_code_empty_returns_default(self):
        self.assertEqual(get_phone_code_from_locale(""), "+55")

    def test_get_phone_code_none_returns_default(self):
        self.assertEqual(get_phone_code_from_locale(None), "+55")

    def test_get_phone_code_invalid_locale_returns_default(self):
        self.assertEqual(get_phone_code_from_locale("invalid"), "+55")

    @patch(
        "retail.agents.shared.country_code_utils.phonenumbers.country_code_for_region"
    )
    def test_get_phone_code_exception_returns_default(self, mock_country_code):
        mock_country_code.side_effect = Exception("Test error")
        self.assertEqual(get_phone_code_from_locale("pt-BR"), "+55")
