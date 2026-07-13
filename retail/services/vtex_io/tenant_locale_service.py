"""Resolve VTEX tenant locale and country from the IO tenants API."""

import logging
from typing import Any, Optional

from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)

TENANT_LOCALE_PATH_TEMPLATE = "/api/tenant/tenants?q={vtex_account}"


def extract_default_locale(response: Any) -> Optional[str]:
    """Extract ``defaultLocale`` from a VTEX tenant API response."""
    if not response:
        return None

    tenant = response if isinstance(response, dict) else None
    if isinstance(response, list) and response:
        tenant = response[0]

    if not tenant:
        return None

    locale = tenant.get("defaultLocale", "")
    return locale or None


def locale_to_geo_country(locale: Optional[str]) -> Optional[str]:
    """Convert a VTEX locale (e.g. ``en-US``) to ISO 3166-1 alpha-2."""
    if not locale or "-" not in locale:
        return None

    region = locale.rsplit("-", 1)[-1].strip()
    return region.upper() if region else None


def language_to_geo_country(language: Optional[str]) -> Optional[str]:
    """Convert a Connect project language (e.g. ``pt-br``) to ISO country code."""
    if not language:
        return None

    return locale_to_geo_country(language.replace("_", "-"))


class VtexTenantLocaleService:
    """Fetches tenant locale via the VTEX IO proxy."""

    def __init__(self, vtex_io_service: Optional[VtexIOService] = None):
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def fetch_default_locale(self, vtex_account: str) -> str:
        """Return the tenant ``defaultLocale`` (e.g. ``pt-BR``) or an empty string."""
        account_domain = f"{vtex_account}.myvtex.com"

        try:
            response = self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                vtex_account=vtex_account,
                method="GET",
                path=TENANT_LOCALE_PATH_TEMPLATE.format(vtex_account=vtex_account),
            )
            locale = extract_default_locale(response)
            if locale:
                return locale
        except Exception as exc:
            logger.warning(
                f"Failed to fetch tenant locale for vtex_account={vtex_account}: {exc}"
            )

        return ""

    def resolve_geo_country(
        self,
        vtex_account: str,
        *,
        fallback_language: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve ISO country code from tenant locale, with optional project fallback."""
        locale = self.fetch_default_locale(vtex_account)
        geo_country = locale_to_geo_country(locale)
        if geo_country:
            return geo_country

        return language_to_geo_country(fallback_language)
