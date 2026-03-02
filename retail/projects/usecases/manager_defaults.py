"""
Language-aware defaults for the Nexus Agent Builder manager attributes.

The mapping key is the language prefix (e.g. "pt", "en", "es") extracted
from Connect's project.language field (e.g. "pt-br" → "pt").
Falls back to "en" when the prefix is not found.
"""

MANAGER_DEFAULTS = {
    "en": {
        "role": "Smart assistant",
        "goal": (
            "Its goal is to answer customer questions, share order status updates, "
            "provide product information, and support sales. Key features include "
            "shopping via WhatsApp and an integrated FAQ."
        ),
    },
    "es": {
        "role": "Asistente inteligente",
        "goal": (
            "Tu objetivo es responder a las preguntas de los clientes, informar el "
            "status de los pedidos, ofrecer información sobre productos y realizar "
            "ventas. Tus principales características incluyen compras vía WhatsApp "
            "y preguntas frecuentes."
        ),
    },
    "pt": {
        "role": "Assistente inteligente",
        "goal": (
            "Seu objetivo é responder às perguntas dos clientes, informar o status "
            "do pedido, fornecer informações sobre produtos e vender. Suas principais "
            "características são: compras via WhatsApp e FAQ."
        ),
    },
}

MANAGER_PERSONALITY = "Amigável"

FALLBACK_LANGUAGE = "en"


def get_manager_defaults(language: str) -> dict:
    """
    Returns translated manager attributes for the given project language.

    Args:
        language: Connect project language (e.g. "pt-br", "en-us", "es").

    Returns:
        Dict with "role" and "goal" keys.
    """
    prefix = (language or "").split("-")[0].lower()
    return MANAGER_DEFAULTS.get(prefix, MANAGER_DEFAULTS[FALLBACK_LANGUAGE])
