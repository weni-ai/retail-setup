from django.test import SimpleTestCase

from retail.agents.domains.agent_integration.usecases.build_back_in_stock_translation import (
    BuildBackInStockTranslationUseCase,
)


META_FOOTER_MAX_LENGTH = 60
META_BUTTON_TEXT_MAX_LENGTH = 25

PT_BR_BODY = (
    "Oi, {{1}}! 👋\n\n"
    "Boa notícia: o *{{2}}* que você queria voltou ao estoque.\n\n"
    "Você pediu pra avisarmos assim que ele chegasse — e já "
    "deixamos seu carrinho pronto, com ele lá dentro. É só tocar "
    "no botão abaixo e finalizar.\n\n"
    "Estoque limitado: vale finalizar antes que ele acabe de novo. 🛒"
)


class BuildBackInStockTranslationTest(SimpleTestCase):
    def test_pt_br_copy_matches_prototype(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="pt_BR",
            button_base_url="https://www.loja.com.br",
            button_url_example="https://www.loja.com.br/apple/p",
            header_image_base64="data:image/png;base64,abc",
        )

        self.assertEqual(result["language"], "pt_BR")
        self.assertEqual(result["category"], "MARKETING")
        self.assertEqual(result["template_body"], PT_BR_BODY)
        self.assertEqual(result["template_body_params"], ["João", "Camiseta Azul"])
        self.assertEqual(
            result["template_footer"],
            "Você recebeu porque pediu aviso de reposição.",
        )
        self.assertEqual(result["template_header"]["header_type"], "IMAGE")

        buttons = result["template_button"]
        self.assertEqual(buttons[0]["type"], "URL")
        self.assertEqual(buttons[0]["text"], "Comprar agora")
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
        self.assertIn("Hi, {{1}}!", result["template_body"])
        self.assertIn("*{{2}}*", result["template_body"])
        self.assertEqual(result["template_button"][0]["text"], "Buy now")
        self.assertEqual(
            result["template_footer"],
            "You received this because you asked for a restock alert.",
        )

    def test_es_copy(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="es",
            button_base_url="https://tienda.com",
            button_url_example="https://tienda.com/apple/p",
        )

        self.assertEqual(result["language"], "es")
        self.assertIn("Hola, {{1}}!", result["template_body"])
        self.assertEqual(result["template_button"][0]["text"], "Comprar ahora")
        self.assertEqual(
            result["template_footer"],
            "Lo recibiste porque pediste aviso de reposición.",
        )

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
        self.assertEqual(result["template_body"], PT_BR_BODY)

    def test_unknown_underscored_language_uses_default_copy(self):
        result = BuildBackInStockTranslationUseCase.build_template_translation(
            language_code="zh_CN",
            button_base_url="https://store.cn",
            button_url_example="https://store.cn/apple/p",
        )

        self.assertEqual(result["language"], "zh_CN")
        self.assertEqual(result["template_body"], PT_BR_BODY)

    def test_footer_and_buttons_fit_meta_limits(self):
        for language_code in ("pt_BR", "en", "es"):
            translation = BuildBackInStockTranslationUseCase.get_translation_or_default(
                language_code
            )
            self.assertLessEqual(
                len(translation["footer_text"]), META_FOOTER_MAX_LENGTH
            )
            self.assertLessEqual(
                len(translation["button_url_text"]), META_BUTTON_TEXT_MAX_LENGTH
            )
            self.assertLessEqual(
                len(translation["button_quick_reply_text"]),
                META_BUTTON_TEXT_MAX_LENGTH,
            )
