from django.test import SimpleTestCase

from retail.agents.domains.agent_integration.usecases.build_back_in_stock_translation import (
    BuildBackInStockTranslationUseCase,
)


class BuildBackInStockTranslationTest(SimpleTestCase):
    def test_pt_br_copy_and_two_body_variables(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            button_base_url="https://www.loja.com.br",
            button_url_example="https://www.loja.com.br/apple/p",
            header_image_base64="data:image/png;base64,abc",
        )

        self.assertEqual(result["language"], "pt_BR")
        self.assertEqual(result["category"], "MARKETING")
        self.assertIn("{{1}}", result["template_body"])
        self.assertIn("{{2}}", result["template_body"])
        self.assertIn("Ótimas notícias", result["template_body"])
        self.assertIn("Toque no botão para comprar", result["template_body"])
        self.assertEqual(result["template_body_params"], ["João", "Camiseta Azul"])
        self.assertEqual(result["template_header"]["header_type"], "IMAGE")

        buttons = result["template_button"]
        self.assertEqual(buttons[0]["type"], "URL")
        self.assertEqual(buttons[0]["text"], "Comprar")
        self.assertEqual(buttons[0]["url"]["base_url"], "https://www.loja.com.br")
        self.assertEqual(buttons[1]["type"], "QUICK_REPLY")
        self.assertEqual(buttons[1]["text"], "Parar promoções")

    def test_en_us_falls_back_to_en(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="en_US",
            button_base_url="https://store.com",
            button_url_example="https://store.com/apple/p",
        )

        self.assertEqual(result["language"], "en")
        self.assertIn("Great news", result["template_body"])
        self.assertEqual(result["template_button"][0]["text"], "Buy")

    def test_es_copy(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="es",
            button_base_url="https://tienda.com",
            button_url_example="https://tienda.com/apple/p",
        )

        self.assertEqual(result["language"], "es")
        self.assertIn("Buenas noticias", result["template_body"])
        self.assertEqual(result["template_button"][0]["text"], "Comprar")

    def test_omits_header_when_image_missing(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            button_base_url="https://www.loja.com.br",
            button_url_example="https://www.loja.com.br/apple/p",
        )

        self.assertNotIn("template_header", result)

    def test_unknown_language_keeps_code_and_uses_default_copy(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="fr",
            button_base_url="https://boutique.fr",
            button_url_example="https://boutique.fr/apple/p",
        )

        self.assertEqual(result["language"], "fr")
        self.assertIn("Ótimas notícias", result["template_body"])

    def test_unknown_underscored_language_uses_default_copy(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="zh_CN",
            button_base_url="https://store.cn",
            button_url_example="https://store.cn/apple/p",
        )

        self.assertEqual(result["language"], "zh_CN")
        self.assertIn("Ótimas notícias", result["template_body"])
