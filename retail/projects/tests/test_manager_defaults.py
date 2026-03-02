from django.test import TestCase

from retail.projects.usecases.manager_defaults import (
    MANAGER_DEFAULTS,
    get_manager_defaults,
)


class TestGetManagerDefaults(TestCase):
    def test_returns_portuguese_for_pt_br(self):
        result = get_manager_defaults("pt-br")
        self.assertEqual(result, MANAGER_DEFAULTS["pt"])

    def test_returns_spanish_for_es(self):
        result = get_manager_defaults("es")
        self.assertEqual(result, MANAGER_DEFAULTS["es"])

    def test_returns_english_for_en_us(self):
        result = get_manager_defaults("en-us")
        self.assertEqual(result, MANAGER_DEFAULTS["en"])

    def test_falls_back_to_english_for_unknown(self):
        result = get_manager_defaults("ja-jp")
        self.assertEqual(result, MANAGER_DEFAULTS["en"])

    def test_falls_back_to_english_for_empty_string(self):
        result = get_manager_defaults("")
        self.assertEqual(result, MANAGER_DEFAULTS["en"])

    def test_falls_back_to_english_for_none(self):
        result = get_manager_defaults(None)
        self.assertEqual(result, MANAGER_DEFAULTS["en"])
