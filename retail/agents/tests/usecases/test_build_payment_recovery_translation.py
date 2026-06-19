import unittest

from retail.agents.domains.agent_integration.usecases.build_payment_recovery_translation import (
    BuildPaymentRecoveryTranslationUseCase,
    PAYMENT_RECOVERY_PIX_PLACEHOLDER,
    PAYMENT_RECOVERY_LINK_PLACEHOLDER,
)


class TestNormalizeLanguageCode(unittest.TestCase):
    def test_exact_match_pt_BR(self):
        result = BuildPaymentRecoveryTranslationUseCase._normalize_language_code(
            "pt_BR"
        )
        self.assertEqual(result, "pt_BR")

    def test_exact_match_en(self):
        result = BuildPaymentRecoveryTranslationUseCase._normalize_language_code("en")
        self.assertEqual(result, "en")

    def test_exact_match_es(self):
        result = BuildPaymentRecoveryTranslationUseCase._normalize_language_code("es")
        self.assertEqual(result, "es")

    def test_fallback_en_US_to_en(self):
        result = BuildPaymentRecoveryTranslationUseCase._normalize_language_code(
            "en_US"
        )
        self.assertEqual(result, "en")

    def test_fallback_es_MX_to_es(self):
        result = BuildPaymentRecoveryTranslationUseCase._normalize_language_code(
            "es_MX"
        )
        self.assertEqual(result, "es")

    def test_unknown_language_returns_as_is(self):
        result = BuildPaymentRecoveryTranslationUseCase._normalize_language_code(
            "fr_FR"
        )
        self.assertEqual(result, "fr_FR")


class TestGetTranslation(unittest.TestCase):
    def test_get_translation_pt_BR(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_translation("pt_BR")
        self.assertIsNotNone(result)
        self.assertIn("João", result["body_example"])
        self.assertEqual(result["footer_text"], "VTEX CX Platform")

    def test_get_translation_en(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_translation("en")
        self.assertIsNotNone(result)
        self.assertIn("John", result["body_example"])

    def test_get_translation_es(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_translation("es")
        self.assertIsNotNone(result)
        self.assertIn("Juan", result["body_example"])

    def test_get_translation_en_US_uses_en(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_translation("en_US")
        self.assertIsNotNone(result)
        self.assertIn("John", result["body_example"])

    def test_get_translation_unknown_returns_none(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_translation("fr_FR")
        self.assertIsNone(result)


class TestGetTranslationOrDefault(unittest.TestCase):
    def test_known_language_returns_translation(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_translation_or_default("en")
        self.assertIn("John", result["body_example"])

    def test_unknown_language_returns_default_pt_BR(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_translation_or_default(
            "fr_FR"
        )
        self.assertIn("João", result["body_example"])


class TestBuildTemplateTranslation(unittest.TestCase):
    def test_build_translation_pt_BR(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
        )
        self.assertEqual(result["language"], "pt_BR")
        self.assertEqual(result["category"], "UTILITY")
        self.assertEqual(result["template_footer"], "VTEX CX Platform")
        self.assertIn("pagamento", result["template_body"])

    def test_build_translation_en_US_normalizes_to_en(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="en_US",
        )
        self.assertEqual(result["language"], "en")
        self.assertIn("payment", result["template_body"])

    def test_build_translation_es_MX_normalizes_to_es(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="es_MX",
        )
        self.assertEqual(result["language"], "es")
        self.assertIn("pago", result["template_body"])

    def test_build_translation_with_header_image(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            header_image_base64="data:image/png;base64,abc123",
        )
        self.assertIn("template_header", result)
        self.assertEqual(result["template_header"]["header_type"], "IMAGE")
        self.assertEqual(
            result["template_header"]["text"], "data:image/png;base64,abc123"
        )

    def test_build_translation_without_header_image(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
        )
        self.assertNotIn("template_header", result)

    def test_build_translation_buttons_are_payment_request(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
        )
        buttons = result["template_button"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["type"], "PAYMENT_REQUEST")
        self.assertEqual(buttons[1]["type"], "PAYMENT_REQUEST")

    def test_build_translation_pix_button_has_payment_setting(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
        )
        pix_button = result["template_button"][0]
        self.assertEqual(pix_button["payment_setting"]["type"], "pix_dynamic_code")
        self.assertEqual(
            pix_button["payment_setting"]["pix_dynamic_code"]["code"],
            PAYMENT_RECOVERY_PIX_PLACEHOLDER,
        )

    def test_build_translation_link_button_has_payment_setting(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
        )
        link_button = result["template_button"][1]
        self.assertEqual(link_button["payment_setting"]["type"], "payment_link")
        self.assertEqual(
            link_button["payment_setting"]["payment_link"]["uri"],
            PAYMENT_RECOVERY_LINK_PLACEHOLDER,
        )

    def test_body_contains_variable_placeholder(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
        )
        self.assertIn("{{1}}", result["template_body"])

    def test_body_params_has_example_name(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="pt_BR",
        )
        self.assertEqual(result["template_body_params"], ["João"])

    def test_unknown_language_uses_default_content(self):
        result = BuildPaymentRecoveryTranslationUseCase.build_template_translation(
            language_code="de_DE",
        )
        self.assertIn("pagamento", result["template_body"])
        self.assertEqual(result["language"], "de_DE")


class TestGetAvailableLanguageCodes(unittest.TestCase):
    def test_returns_all_available_codes(self):
        result = BuildPaymentRecoveryTranslationUseCase.get_available_language_codes()
        self.assertIn("pt_BR", result)
        self.assertIn("en", result)
        self.assertIn("es", result)
        self.assertEqual(len(result), 3)
