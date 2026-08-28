"""Translations for the back-in-stock WhatsApp marketing template."""

from typing import Any, Dict, Optional

from retail.agents.shared.country_code_utils import DEFAULT_TEMPLATE_LANGUAGE


class BuildBackInStockTranslationUseCase:
    """Build back-in-stock template translations for Meta/WhatsApp."""

    _TRANSLATIONS: Dict[str, Dict[str, Any]] = {
        "pt_BR": {
            "body_text": (
                "Oi, {{1}}! 👋\n\n"
                "Boa notícia: o *{{2}}* que você queria voltou ao estoque.\n\n"
                "Você pediu pra avisarmos assim que ele chegasse — e já "
                "deixamos seu carrinho pronto, com ele lá dentro. É só tocar "
                "no botão abaixo e finalizar.\n\n"
                "Estoque limitado: vale finalizar antes que ele acabe de novo. 🛒"
            ),
            "body_example": ["João", "Camiseta Azul"],
            "footer_text": "Você recebeu porque pediu aviso de reposição.",
            "button_url_text": "Comprar agora",
            "button_quick_reply_text": "Parar promoções",
        },
        "en": {
            "body_text": (
                "Hi, {{1}}! 👋\n\n"
                "Good news: *{{2}}* that you wanted is back in stock.\n\n"
                "You asked us to let you know when it arrived — and we already "
                "left your cart ready, with it inside. Just tap the button "
                "below to check out.\n\n"
                "Limited stock: worth finishing before it's gone again. 🛒"
            ),
            "body_example": ["John", "Blue T-shirt"],
            "footer_text": "You received this because you asked for a restock alert.",
            "button_url_text": "Buy now",
            "button_quick_reply_text": "Stop promotions",
        },
        "es": {
            "body_text": (
                "Hola, {{1}}! 👋\n\n"
                "Buenas noticias: *{{2}}* que querías volvió al stock.\n\n"
                "Pediste que te avisáramos en cuanto llegara — y ya dejamos "
                "tu carrito listo, con él dentro. Toca el botón de abajo "
                "para finalizar.\n\n"
                "Stock limitado: conviene finalizar antes de que se agote otra vez. 🛒"
            ),
            "body_example": ["Juan", "Camiseta azul"],
            "footer_text": "Lo recibiste porque pediste aviso de reposición.",
            "button_url_text": "Comprar ahora",
            "button_quick_reply_text": "Parar promociones",
        },
    }

    @classmethod
    def _normalize_language_code(cls, language_code: str) -> str:
        if language_code in cls._TRANSLATIONS:
            return language_code
        if "_" in language_code:
            base_code = language_code.split("_")[0]
            if base_code in cls._TRANSLATIONS:
                return base_code
        return language_code

    @classmethod
    def get_translation(cls, language_code: str) -> Optional[Dict[str, Any]]:
        return cls._TRANSLATIONS.get(cls._normalize_language_code(language_code))

    @classmethod
    def get_translation_or_default(cls, language_code: str) -> Dict[str, Any]:
        translation = cls.get_translation(language_code)
        if translation is None:
            return cls._TRANSLATIONS[DEFAULT_TEMPLATE_LANGUAGE]
        return translation

    @classmethod
    def build_template_translation(
        cls,
        language_code: str,
        button_base_url: str,
        button_url_example: str,
        header_image_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the payload expected by CreateCustomTemplateUseCase."""
        normalized_code = cls._normalize_language_code(language_code)
        translation_data = cls.get_translation_or_default(language_code)

        template_translation: Dict[str, Any] = {
            "template_body": translation_data["body_text"],
            "template_body_params": translation_data["body_example"],
            "template_footer": translation_data["footer_text"],
            "template_button": [
                {
                    "type": "URL",
                    "text": translation_data["button_url_text"],
                    "url": {
                        "base_url": button_base_url,
                        "url_suffix_example": button_url_example,
                    },
                },
                {
                    "type": "QUICK_REPLY",
                    "text": translation_data["button_quick_reply_text"],
                },
            ],
            "category": "MARKETING",
            "language": normalized_code,
        }

        if header_image_base64:
            template_translation["template_header"] = {
                "header_type": "IMAGE",
                "text": header_image_base64,
            }

        return template_translation
