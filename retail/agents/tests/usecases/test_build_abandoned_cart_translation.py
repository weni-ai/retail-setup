import unittest

from retail.agents.domains.agent_integration.usecases.build_abandoned_cart_translation import (
    BuildAbandonedCartTranslationUseCase,
)


class TestNormalizeLanguageCode(unittest.TestCase):
    """Tests for language code normalization."""

    def test_exact_match_pt_BR(self):
        """pt_BR should match exactly."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("pt_BR")
        self.assertEqual(result, "pt_BR")

    def test_exact_match_en(self):
        """en should match exactly."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("en")
        self.assertEqual(result, "en")

    def test_exact_match_es(self):
        """es should match exactly."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("es")
        self.assertEqual(result, "es")

    def test_fallback_en_US_to_en(self):
        """en_US should fallback to en."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("en_US")
        self.assertEqual(result, "en")

    def test_fallback_en_GB_to_en(self):
        """en_GB should fallback to en."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("en_GB")
        self.assertEqual(result, "en")

    def test_fallback_es_MX_to_es(self):
        """es_MX should fallback to es."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("es_MX")
        self.assertEqual(result, "es")

    def test_fallback_es_AR_to_es(self):
        """es_AR should fallback to es."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("es_AR")
        self.assertEqual(result, "es")

    def test_fallback_es_CL_to_es(self):
        """es_CL should fallback to es."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("es_CL")
        self.assertEqual(result, "es")

    def test_fallback_es_CO_to_es(self):
        """es_CO should fallback to es."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("es_CO")
        self.assertEqual(result, "es")

    def test_unknown_language_returns_as_is(self):
        """Unknown language code returns as-is."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("fr_FR")
        self.assertEqual(result, "fr_FR")

    def test_unknown_simple_code_returns_as_is(self):
        """Unknown simple language code returns as-is."""
        result = BuildAbandonedCartTranslationUseCase._normalize_language_code("de")
        self.assertEqual(result, "de")


class TestGetTranslation(unittest.TestCase):
    """Tests for getting translations."""

    def test_get_translation_pt_BR(self):
        """Should return Portuguese translation for pt_BR."""
        result = BuildAbandonedCartTranslationUseCase.get_translation("pt_BR")
        self.assertIsNotNone(result)
        self.assertIn("João", result["body_example"])
        self.assertIn("Finalizar Pedido", result["footer_text"])

    def test_get_translation_en(self):
        """Should return English translation for en."""
        result = BuildAbandonedCartTranslationUseCase.get_translation("en")
        self.assertIsNotNone(result)
        self.assertIn("John", result["body_example"])
        self.assertIn("Finish Order", result["footer_text"])

    def test_get_translation_es(self):
        """Should return Spanish translation for es."""
        result = BuildAbandonedCartTranslationUseCase.get_translation("es")
        self.assertIsNotNone(result)
        self.assertIn("Juan", result["body_example"])

    def test_get_translation_en_US_uses_en(self):
        """en_US should return English translation."""
        result = BuildAbandonedCartTranslationUseCase.get_translation("en_US")
        self.assertIsNotNone(result)
        self.assertIn("John", result["body_example"])

    def test_get_translation_es_MX_uses_es(self):
        """es_MX should return Spanish translation."""
        result = BuildAbandonedCartTranslationUseCase.get_translation("es_MX")
        self.assertIsNotNone(result)
        self.assertIn("Juan", result["body_example"])

    def test_get_translation_unknown_returns_none(self):
        """Unknown language should return None."""
        result = BuildAbandonedCartTranslationUseCase.get_translation("fr_FR")
        self.assertIsNone(result)


class TestGetTranslationOrDefault(unittest.TestCase):
    """Tests for getting translations with fallback to default."""

    def test_known_language_returns_translation(self):
        """Known language should return its translation."""
        result = BuildAbandonedCartTranslationUseCase.get_translation_or_default("en")
        self.assertIn("John", result["body_example"])

    def test_normalized_language_returns_translation(self):
        """Normalized language (es_AR -> es) should return translation."""
        result = BuildAbandonedCartTranslationUseCase.get_translation_or_default(
            "es_AR"
        )
        self.assertIn("Juan", result["body_example"])

    def test_unknown_language_returns_default_pt_BR(self):
        """Unknown language should fallback to default (pt_BR)."""
        result = BuildAbandonedCartTranslationUseCase.get_translation_or_default(
            "fr_FR"
        )
        self.assertIn("João", result["body_example"])

    def test_empty_language_returns_default(self):
        """Empty language should return default."""
        result = BuildAbandonedCartTranslationUseCase.get_translation_or_default("")
        self.assertIn("João", result["body_example"])


class TestBuildTemplateTranslation(unittest.TestCase):
    """Tests for building template translation payloads."""

    def test_build_template_translation_pt_BR(self):
        """Should build correct payload for pt_BR."""
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "pt_BR")
        self.assertEqual(result["category"], "MARKETING")
        self.assertIn("Finalizar Pedido", result["template_footer"])

    def test_build_template_translation_en_US_normalizes_to_en(self):
        """en_US should be normalized to en in payload."""
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code="en_US",
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "en")
        self.assertIn("Finish Order", result["template_footer"])

    def test_build_template_translation_es_MX_normalizes_to_es(self):
        """es_MX should be normalized to es in payload."""
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code="es_MX",
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "es")

    def test_build_template_translation_with_header_image(self):
        """Should include header image when provided."""
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
            header_image_base64="base64encodedimage",
        )
        self.assertIn("template_header", result)
        self.assertEqual(result["template_header"]["header_type"], "IMAGE")
        self.assertEqual(result["template_header"]["text"], "base64encodedimage")

    def test_build_template_translation_without_header_image(self):
        """Should not include header when not provided."""
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertNotIn("template_header", result)

    def test_build_template_translation_buttons_structure(self):
        """Should have correct button structure."""
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        buttons = result["template_button"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["type"], "URL")
        self.assertEqual(buttons[0]["url"]["base_url"], "https://store.com/checkout")
        self.assertEqual(buttons[1]["type"], "QUICK_REPLY")


class TestBuildIntegrationsTranslation(unittest.TestCase):
    """Tests for building integrations service format payloads."""

    def test_build_integrations_translation_pt_BR(self):
        """Should build correct payload for pt_BR."""
        result = BuildAbandonedCartTranslationUseCase.build_integrations_translation(
            language_code="pt_BR",
            button_url="https://store.com/checkout/{{1}}",
            button_url_example="https://store.com/checkout/12345",
        )
        self.assertEqual(result["language"], "pt_BR")
        self.assertEqual(result["body"]["type"], "BODY")
        self.assertEqual(result["footer"]["type"], "FOOTER")

    def test_build_integrations_translation_en_US_normalizes_to_en(self):
        """en_US should be normalized to en in payload."""
        result = BuildAbandonedCartTranslationUseCase.build_integrations_translation(
            language_code="en_US",
            button_url="https://store.com/checkout/{{1}}",
            button_url_example="https://store.com/checkout/12345",
        )
        self.assertEqual(result["language"], "en")

    def test_build_integrations_translation_es_AR_normalizes_to_es(self):
        """es_AR should be normalized to es in payload."""
        result = BuildAbandonedCartTranslationUseCase.build_integrations_translation(
            language_code="es_AR",
            button_url="https://store.com/checkout/{{1}}",
            button_url_example="https://store.com/checkout/12345",
        )
        self.assertEqual(result["language"], "es")

    def test_build_integrations_translation_buttons_structure(self):
        """Should have correct button structure for integrations format."""
        result = BuildAbandonedCartTranslationUseCase.build_integrations_translation(
            language_code="pt_BR",
            button_url="https://store.com/checkout/{{1}}",
            button_url_example="https://store.com/checkout/12345",
        )
        buttons = result["buttons"]
        self.assertEqual(len(buttons), 2)
        self.assertEqual(buttons[0]["button_type"], "URL")
        self.assertEqual(buttons[0]["url"], "https://store.com/checkout/{{1}}")
        self.assertEqual(buttons[1]["button_type"], "QUICK_REPLY")


class TestGetAvailableLanguageCodes(unittest.TestCase):
    """Tests for getting available language codes."""

    def test_returns_all_available_codes(self):
        """Should return all configured language codes."""
        result = BuildAbandonedCartTranslationUseCase.get_available_language_codes()
        self.assertIn("pt_BR", result)
        self.assertIn("en", result)
        self.assertIn("es", result)
        self.assertEqual(len(result), 3)


class TestLanguageConversionIntegration(unittest.TestCase):
    """Integration tests for complete language conversion flow."""

    def test_vtex_pt_BR_to_meta_template(self):
        """VTEX pt-BR converted to pt_BR should work correctly."""
        # Simulating: VTEX returns "pt-BR" -> converted to "pt_BR" -> used in template
        meta_language = "pt_BR"  # After conversion from "pt-BR"
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code=meta_language,
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "pt_BR")
        self.assertIn("carrinho", result["template_body"])

    def test_vtex_en_US_to_meta_template(self):
        """VTEX en-US converted to en_US should fallback to en."""
        # Simulating: VTEX returns "en-US" -> converted to "en_US" -> used in template
        meta_language = "en_US"  # After conversion from "en-US"
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code=meta_language,
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "en")
        self.assertIn("cart", result["template_body"])

    def test_vtex_es_MX_to_meta_template(self):
        """VTEX es-MX converted to es_MX should fallback to es."""
        # Simulating: VTEX returns "es-MX" -> converted to "es_MX" -> used in template
        meta_language = "es_MX"  # After conversion from "es-MX"
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code=meta_language,
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "es")
        self.assertIn("carrito", result["template_body"])

    def test_vtex_es_AR_to_meta_template(self):
        """VTEX es-AR converted to es_AR should fallback to es."""
        meta_language = "es_AR"
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code=meta_language,
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "es")

    def test_vtex_es_CL_to_meta_template(self):
        """VTEX es-CL converted to es_CL should fallback to es."""
        meta_language = "es_CL"
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code=meta_language,
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        self.assertEqual(result["language"], "es")

    def test_unknown_language_uses_default_pt_BR(self):
        """Unknown language should fallback to pt_BR content."""
        meta_language = "de_DE"  # German - not supported
        result = BuildAbandonedCartTranslationUseCase.build_template_translation(
            language_code=meta_language,
            button_base_url="https://store.com/checkout",
            button_url_example="12345",
        )
        # Should use pt_BR content (fallback)
        self.assertIn("carrinho", result["template_body"])
        # But language field uses the normalized code (de_DE since no match)
        self.assertEqual(result["language"], "de_DE")
