"""
Utility functions for extracting country phone codes and language codes from VTEX locale.
"""

import logging
import phonenumbers

logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_LANGUAGE = "pt_BR"


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


def convert_vtex_locale_to_meta_language(locale: str) -> str:
    """
    Convert VTEX locale to Meta language code.

    Simply replaces '-' with '_' to convert from VTEX format to Meta format.
    Meta supports locale codes like: pt_BR, es_MX, es_AR, en_US, etc.

    Args:
        locale: VTEX locale (e.g., 'pt-BR', 'es-MX', 'en-US')

    Returns:
        Meta language code (e.g., 'pt_BR', 'es_MX', 'en_US')

    Examples:
        >>> convert_vtex_locale_to_meta_language('pt-BR')
        'pt_BR'
        >>> convert_vtex_locale_to_meta_language('es-MX')
        'es_MX'
        >>> convert_vtex_locale_to_meta_language('en-US')
        'en_US'
    """
    if not locale:
        return DEFAULT_TEMPLATE_LANGUAGE

    # Simply replace '-' with '_' to convert VTEX format to Meta format
    return locale.replace("-", "_")


DEFAULT_CONNECT_LANGUAGE = "pt-br"


def convert_vtex_locale_to_connect_language(locale: str) -> str:
    """
    Convert VTEX locale to Connect project language format.

    VTEX returns locale as 'pt-BR'; Connect expects the same string
    lowercased ('pt-br').  Works for any locale, not just a fixed set.

    Args:
        locale: VTEX locale (e.g., 'pt-BR', 'en-US', 'es-AR')

    Returns:
        Connect language code (e.g., 'pt-br', 'en-us', 'es-ar')

    Examples:
        >>> convert_vtex_locale_to_connect_language('pt-BR')
        'pt-br'
        >>> convert_vtex_locale_to_connect_language('en-US')
        'en-us'
        >>> convert_vtex_locale_to_connect_language('es-AR')
        'es-ar'
    """
    if not locale:
        return DEFAULT_CONNECT_LANGUAGE

    return locale.lower()


def convert_connect_language_to_meta(language: str) -> str:
    """
    Convert Connect language format to Meta language format.

    Useful for converting stored project language to Meta's expected format.

    Args:
        language: Connect language (e.g., 'pt-br', 'en-us', 'es')

    Returns:
        Meta language code (e.g., 'pt_BR', 'en_US', 'es')

    Examples:
        >>> convert_connect_language_to_meta('pt-br')
        'pt_BR'
        >>> convert_connect_language_to_meta('en-us')
        'en_US'
        >>> convert_connect_language_to_meta('es')
        'es'
    """
    if not language:
        return DEFAULT_TEMPLATE_LANGUAGE

    parts = language.split("-")
    if len(parts) == 2:
        return f"{parts[0]}_{parts[1].upper()}"
    return parts[0]


def get_country_phone_code_from_locale(locale: str) -> str:
    """
    Get the country phone code (DDI) from a VTEX locale string.

    Uses phonenumbers library to get the correct country calling code.

    Args:
        locale: VTEX locale (e.g., 'pt-BR', 'es-AR', 'en-US')

    Returns:
        Country phone code without + prefix (e.g., '55', '54', '1')

    Examples:
        >>> get_country_phone_code_from_locale('pt-BR')
        '55'
        >>> get_country_phone_code_from_locale('es-AR')
        '54'
        >>> get_country_phone_code_from_locale('en-US')
        '1'
    """
    region = extract_region_from_locale(locale)

    try:
        country_code = phonenumbers.country_code_for_region(region)
        if country_code:
            return str(country_code)
    except Exception as e:
        logger.warning(
            f"Failed to get phone code for region={region} locale={locale}: {e}"
        )

    # Default to Brazil
    return "55"
