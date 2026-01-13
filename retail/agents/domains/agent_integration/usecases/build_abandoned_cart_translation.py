"""
Use case for building abandoned cart template translations.

This module provides translations for abandoned cart templates
in multiple languages supported by Meta/WhatsApp.
"""

from typing import Dict, Any, Optional

from retail.agents.shared.country_code_utils import DEFAULT_TEMPLATE_LANGUAGE


class BuildAbandonedCartTranslationUseCase:
    """
    Use case for building abandoned cart template translations.

    Provides translations for different languages and builds
    the translation payload for template creation.
    """

    # Translation data organized by language code
    _TRANSLATIONS: Dict[str, Dict[str, Any]] = {
        "pt_BR": {
            "body_text": (
                "Olá, {{1}} vimos que você deixou itens no seu carrinho 🛒. "
                "\nVamos fechar o pedido e garantir essas ofertas? "
                "\n\nClique em Finalizar Pedido para concluir sua compra 👇"
            ),
            "body_example": ["João"],
            "footer_text": "Finalizar Pedido",
            "button_url_text": "Finalizar Pedido",
            "button_quick_reply_text": "Parar Promoções",
        },
        "en": {
            "body_text": (
                "Hello, {{1}} we noticed you left items in your cart 🛒. "
                "\nReady to complete your order and secure these deals? "
                "\n\nClick Finish Order to complete your purchase 👇"
            ),
            "body_example": ["John"],
            "footer_text": "Finish Order",
            "button_url_text": "Finish Order",
            "button_quick_reply_text": "Stop Promotions",
        },
        "es": {
            "body_text": (
                "Hola, {{1}} notamos que dejaste artículos en tu carrito 🛒. "
                "\n¿Listo para completar tu pedido y asegurar estas ofertas? "
                "\n\nHaz clic en Finalizar Pedido para completar tu compra 👇"
            ),
            "body_example": ["Juan"],
            "footer_text": "Finalizar Pedido",
            "button_url_text": "Finalizar Pedido",
            "button_quick_reply_text": "Parar Promociones",
        },
    }

    @classmethod
    def _normalize_language_code(cls, language_code: str) -> str:
        """
        Normalize language code to match available translations.

        Tries exact match first, then falls back to base language code.
        Example: 'en_US' -> 'en', 'es_MX' -> 'es'

        Args:
            language_code: The Meta language code (e.g., 'pt_BR', 'en_US', 'es_MX')

        Returns:
            Normalized language code that matches available translations.
        """
        # Try exact match first
        if language_code in cls._TRANSLATIONS:
            return language_code

        # Try base language code (e.g., 'en_US' -> 'en')
        if "_" in language_code:
            base_code = language_code.split("_")[0]
            if base_code in cls._TRANSLATIONS:
                return base_code

        return language_code

    @classmethod
    def get_translation(cls, language_code: str) -> Optional[Dict[str, Any]]:
        """
        Get translation data for a specific language.

        Tries exact match first, then falls back to base language code.
        Example: 'es_AR' -> tries 'es_AR', then 'es'

        Args:
            language_code: The Meta language code (e.g., 'pt_BR', 'en_US', 'es_MX')

        Returns:
            Translation dictionary if found, None otherwise.
        """
        normalized_code = cls._normalize_language_code(language_code)
        return cls._TRANSLATIONS.get(normalized_code)

    @classmethod
    def get_translation_or_default(cls, language_code: str) -> Dict[str, Any]:
        """
        Get translation data for a language, falling back to default if not found.

        Tries exact match first, then falls back to base language code.
        If still not found, returns default (pt_BR) translation.

        This allows templates to be created even for unsupported languages,
        and users can later edit the template language via the languages API.

        Args:
            language_code: The Meta language code (e.g., 'pt_BR', 'en_US', 'es_MX')

        Returns:
            Translation dictionary for the language or default (pt_BR).
        """
        translation = cls.get_translation(language_code)
        if translation is None:
            translation = cls._TRANSLATIONS[DEFAULT_TEMPLATE_LANGUAGE]
        return translation

    @classmethod
    def build_template_translation(
        cls,
        language_code: str,
        button_base_url: str,
        button_url_example: str,
        header_image_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a complete template translation payload for template creation.

        This method builds the translation in the format expected by
        CreateCustomTemplateUseCase's TemplateMetadataHandler.

        Args:
            language_code: The Meta language code (e.g., 'pt_BR', 'en_US', 'es_MX')
            button_base_url: Base URL for the checkout button
            button_url_example: Example URL with order form ID
            header_image_base64: Optional base64 encoded header image

        Returns:
            Translation dictionary ready for template creation.
        """
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

        # Add header image if provided
        if header_image_base64:
            template_translation["template_header"] = {
                "header_type": "IMAGE",
                "text": header_image_base64,
            }

        return template_translation

    @classmethod
    def build_integrations_translation(
        cls,
        language_code: str,
        button_url: str,
        button_url_example: str,
    ) -> Dict[str, Any]:
        """
        Build a translation payload for IntegrationsService format.

        This format is used by the legacy create_abandoned_cart_template method
        in IntegrationsService.

        Args:
            language_code: The Meta language code (e.g., 'pt_BR', 'en_US', 'es_MX')
            button_url: Full URL with variable placeholder for checkout
            button_url_example: Example URL with order form ID

        Returns:
            Translation dictionary in IntegrationsService format.
        """
        normalized_code = cls._normalize_language_code(language_code)
        translation_data = cls.get_translation_or_default(language_code)

        return {
            "language": normalized_code,
            "body": {
                "type": "BODY",
                "text": translation_data["body_text"],
                "example": {"body_text": [translation_data["body_example"]]},
            },
            "footer": {"type": "FOOTER", "text": translation_data["footer_text"]},
            "buttons": [
                {
                    "button_type": "URL",
                    "text": translation_data["button_url_text"],
                    "url": button_url,
                    "example": [button_url_example],
                },
                {
                    "button_type": "QUICK_REPLY",
                    "text": translation_data["button_quick_reply_text"],
                },
            ],
        }

    @classmethod
    def get_available_language_codes(cls) -> list:
        """
        Get list of language codes that have translations available.

        Returns:
            List of available language code strings.
        """
        return list(cls._TRANSLATIONS.keys())
