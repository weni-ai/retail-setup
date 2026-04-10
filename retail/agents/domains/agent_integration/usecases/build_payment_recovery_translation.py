"""
Use case for building payment recovery template translations.

This module provides translations for payment recovery templates
in multiple languages supported by Meta/WhatsApp.
"""

from typing import Dict, Any, Optional

from retail.agents.shared.country_code_utils import DEFAULT_TEMPLATE_LANGUAGE


PAYMENT_RECOVERY_PIX_PLACEHOLDER = (
    "00020101021226700014br.gov.bcb.pix2548pix.example.com/qr/v3/"
    "at/4376b932-1234-4abc-8def-1234567890ab5204000053039865802BR"
)
PAYMENT_RECOVERY_LINK_PLACEHOLDER = "https://my-payment-link-url"


class BuildPaymentRecoveryTranslationUseCase:
    """
    Builds payment recovery template translations for Meta/WhatsApp.

    Provides translations in pt_BR, en and es, with PAYMENT_REQUEST
    buttons (Pix + payment link).
    """

    _TRANSLATIONS: Dict[str, Dict[str, Any]] = {
        "pt_BR": {
            "body_text": (
                "Olá, {{1}}! Identificamos que o pagamento do seu pedido "
                "não foi finalizado. Mas não se preocupe — seu carrinho "
                "ainda está guardado. Escolha como prefere concluir sua compra:"
            ),
            "body_example": ["João"],
            "footer_text": "VTEX CX Platform",
            "button_pix_text": "Copiar código Pix",
            "button_link_text": "Outros métodos de pagamento",
        },
        "en": {
            "body_text": (
                "Hello, {{1}}! We noticed your order payment wasn't "
                "completed. Don't worry — your cart is still saved. "
                "Choose how you'd like to finish your purchase:"
            ),
            "body_example": ["John"],
            "footer_text": "VTEX CX Platform",
            "button_pix_text": "Copy Pix code",
            "button_link_text": "Other payment methods",
        },
        "es": {
            "body_text": (
                "Hola, {{1}}! Identificamos que el pago de tu pedido "
                "no fue finalizado. No te preocupes — tu carrito "
                "aún está guardado. Elige cómo prefieres completar tu compra:"
            ),
            "body_example": ["Juan"],
            "footer_text": "VTEX CX Platform",
            "button_pix_text": "Copiar código Pix",
            "button_link_text": "Otros métodos de pago",
        },
    }

    @classmethod
    def _normalize_language_code(cls, language_code: str) -> str:
        """
        Normalize language code to match available translations.

        Tries exact match first, then falls back to base language code.
        Example: 'en_US' -> 'en', 'es_MX' -> 'es'
        """
        if language_code in cls._TRANSLATIONS:
            return language_code

        if "_" in language_code:
            base_code = language_code.split("_")[0]
            if base_code in cls._TRANSLATIONS:
                return base_code

        return language_code

    @classmethod
    def get_translation(cls, language_code: str) -> Optional[Dict[str, Any]]:
        """Get translation data for a specific language."""
        normalized_code = cls._normalize_language_code(language_code)
        return cls._TRANSLATIONS.get(normalized_code)

    @classmethod
    def get_translation_or_default(cls, language_code: str) -> Dict[str, Any]:
        """Get translation data, falling back to default (pt_BR) if not found."""
        translation = cls.get_translation(language_code)
        if translation is None:
            translation = cls._TRANSLATIONS[DEFAULT_TEMPLATE_LANGUAGE]
        return translation

    @classmethod
    def build_template_translation(
        cls,
        language_code: str,
        header_image_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Build a complete template translation payload for template creation.

        Uses PAYMENT_REQUEST buttons with placeholder payment data
        for template approval. Real payment data is provided at send time.

        Args:
            language_code: The Meta language code (e.g., 'pt_BR', 'en_US', 'es_MX')
            header_image_base64: Optional base64 encoded header image

        Returns:
            Translation dictionary ready for CreateCustomTemplateUseCase.
        """
        normalized_code = cls._normalize_language_code(language_code)
        translation_data = cls.get_translation_or_default(language_code)

        template_translation: Dict[str, Any] = {
            "template_body": translation_data["body_text"],
            "template_body_params": translation_data["body_example"],
            "template_footer": translation_data["footer_text"],
            "template_button": [
                {
                    "type": "PAYMENT_REQUEST",
                    "text": translation_data["button_pix_text"],
                    "payment_setting": {
                        "type": "pix_dynamic_code",
                        "pix_dynamic_code": {
                            "code": PAYMENT_RECOVERY_PIX_PLACEHOLDER,
                        },
                    },
                },
                {
                    "type": "PAYMENT_REQUEST",
                    "text": translation_data["button_link_text"],
                    "payment_setting": {
                        "type": "payment_link",
                        "payment_link": {
                            "uri": PAYMENT_RECOVERY_LINK_PLACEHOLDER,
                        },
                    },
                },
            ],
            "category": "UTILITY",
            "language": normalized_code,
        }

        if header_image_base64:
            template_translation["template_header"] = {
                "header_type": "IMAGE",
                "text": header_image_base64,
            }

        return template_translation

    @classmethod
    def get_available_language_codes(cls) -> list:
        """Get list of language codes that have translations available."""
        return list(cls._TRANSLATIONS.keys())
