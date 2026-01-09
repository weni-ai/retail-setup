"""
Utility functions for extracting country phone codes from VTEX locale.
"""

import logging
import phonenumbers

logger = logging.getLogger(__name__)


def extract_region_from_locale(locale: str) -> str:
    """
    Extract region code from VTEX locale string.

    Args:
        locale: VTEX locale (e.g., 'pt-BR', 'es-AR', 'en-US')

    Returns:
        Region code (e.g., 'BR', 'AR', 'US') or 'BR' as default.

    Examples:
        >>> extract_region_from_locale('pt-BR')
        'BR'
        >>> extract_region_from_locale('es-AR')
        'AR'
    """
    if not locale or "-" not in locale:
        return "BR"

    parts = locale.split("-")
    return parts[-1].upper() if len(parts) >= 2 else "BR"


def get_phone_code_from_locale(locale: str) -> str:
    """
    Get the international phone code from a VTEX locale string.

    Uses phonenumbers library to get the correct country calling code.

    Args:
        locale: VTEX locale (e.g., 'pt-BR', 'es-AR', 'en-US')

    Returns:
        Phone code with + prefix (e.g., '+55', '+54', '+1')

    Examples:
        >>> get_phone_code_from_locale('pt-BR')
        '+55'
        >>> get_phone_code_from_locale('es-AR')
        '+54'
        >>> get_phone_code_from_locale('en-US')
        '+1'
    """
    region = extract_region_from_locale(locale)

    try:
        country_code = phonenumbers.country_code_for_region(region)
        if country_code:
            return f"+{country_code}"
    except Exception as e:
        logger.warning(
            f"Failed to get phone code for region={region} locale={locale}: {e}"
        )

    # Default to Brazil
    return "+55"
