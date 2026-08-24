"""Shared helpers for VTEX sub-account detection."""

from typing import Any, Dict, List, Optional

from retail.projects.models import Project

VTEX_CONFIG_KEY = "vtex_config"
VTEX_SUB_ACCOUNTS_KEY = "vtex_sub_accounts"
LEGACY_VTEX_STORES_KEY = "vtex_stores"
# License Manager endpoint; VTEX names this resource "stores".
VTEX_ACCOUNT_STORES_PATH = "/api/vlm/account/stores"

ORDER_ORIGIN_CACHE_KEY_PREFIX = "order_origin_account"
ORDER_ORIGIN_CACHE_TIMEOUT_SECONDS = 3600


def _vtex_config(project: Project) -> Dict[str, Any]:
    config = getattr(project, "config", None)
    if not isinstance(config, dict):
        return {}
    vtex_config = config.get(VTEX_CONFIG_KEY)
    if not isinstance(vtex_config, dict):
        return {}
    return vtex_config


def _account_names_from_config_list(raw: Any) -> List[str]:
    if not isinstance(raw, list):
        return []

    names: List[str] = []
    for item in raw:
        if isinstance(item, str) and item:
            names.append(item)
            continue
        if isinstance(item, dict):
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
    return names


def read_vtex_sub_accounts(project: Project) -> List[str]:
    """Return stored VTEX sub-account names from ``project.config``.

    Prefers ``vtex_sub_accounts``. Also reads the previous ``vtex_stores``
    key (names or ``{name, hosts}`` objects) so already-synced projects
    keep working until the next sync.
    """
    vtex_config = _vtex_config(project)
    names = _account_names_from_config_list(vtex_config.get(VTEX_SUB_ACCOUNTS_KEY))
    if names:
        return names
    return _account_names_from_config_list(vtex_config.get(LEGACY_VTEX_STORES_KEY))


def project_has_multiple_vtex_accounts(project: Project) -> bool:
    """Return True when more than one VTEX sub-account was persisted."""
    return len(read_vtex_sub_accounts(project)) > 1


def origin_account_from_hostname(
    hostname: str, account_names: Optional[List[str]] = None
) -> str:
    """Return the stored sub-account name that matches OMS ``hostname``."""
    if not hostname:
        return hostname

    normalized = hostname.strip().lower()
    for name in account_names or []:
        if name.strip().lower() == normalized:
            return name
    return hostname
