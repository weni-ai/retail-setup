"""Translations for the back-in-stock WhatsApp marketing template."""

from typing import Any, Dict, Optional

from retail.agents.shared.country_code_utils import DEFAULT_TEMPLATE_LANGUAGE


class BuildBackInStockTranslationUseCase:
    """Build back-in-stock template translations for Meta/WhatsApp."""

    _TRANSLATIONS: Dict[str, Dict[str, Any]] = {
        "pt_BR": {
            "body_text": (
                "Ótimas notícias, {{1}}. {{2}} já está de volta ao estoque. "
                "Toque no botão para comprar"
            ),
            "body_example": ["João", "Camiseta Azul"],
            "button_url_text": "Comprar",
            "button_quick_reply_text": "Parar promoções",
        },
        "en": {
            "body_text": (
                "Great news, {{1}}. {{2}} is back in stock. " "Tap the button to buy it"
            ),
            "body_example": ["John", "Blue T-shirt"],
            "button_url_text": "Buy",
            "button_quick_reply_text": "Stop promotions",
        },
        "es": {
            "body_text": (
                "Buenas noticias, {{1}}. {{2}} ya está de vuelta en stock. "
                "Toca el botón para comprarlo"
            ),
            "body_example": ["Juan", "Camiseta azul"],
            "button_url_text": "Comprar",
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
