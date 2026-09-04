"""Detect VTEX sub-accounts and persist the names on the project."""

import logging
from dataclasses import dataclass
from typing import Any, List, Optional, Tuple

from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.sub_accounts import (
    LEGACY_VTEX_STORES_KEY,
    VTEX_ACCOUNT_STORES_PATH,
    VTEX_CONFIG_KEY,
    VTEX_SUB_ACCOUNTS_KEY,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class VtexSubAccountsSyncResult:
    """Sub-account names returned by License Manager for one project."""

    sub_accounts: Tuple[str, ...]

    @property
    def has_multiple_vtex_accounts(self) -> bool:
        return len(self.sub_accounts) > 1


class SyncVtexSubAccountsUseCase:
    """Fetch ``GET /api/vlm/account/stores`` and store the names on the project.

    Fail-safe: infrastructure errors are logged and return ``None`` so agent
    assignment never fails because this check is unavailable.
    """

    def __init__(self, vtex_io_service: Optional[VtexIOService] = None):
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def execute(self, project: Project) -> Optional[VtexSubAccountsSyncResult]:
        """Fetch License Manager names and write them on ``project.config``.

        Args:
            project: Project whose ``vtex_account`` is queried.

        Returns:
            The parsed result, or None when the project has no account or
            the VTEX call fails.
        """
        sub_accounts = self.fetch_sub_accounts(project)
        if sub_accounts is None:
            return None

        result = VtexSubAccountsSyncResult(sub_accounts=tuple(sub_accounts))
        self._persist(project, result)
        return result

    def fetch_sub_accounts(self, project: Project) -> Optional[List[str]]:
        """Return License Manager account names, or None on skip/failure."""
        vtex_account = project.vtex_account
        if not vtex_account:
            logger.info(
                f"[VTEX_SUB_ACCOUNTS] skipped_no_account: project={project.uuid}"
            )
            return None

        account_domain = f"{vtex_account}.myvtex.com"
        try:
            logger.info(
                f"[VTEX_SUB_ACCOUNTS] fetching: "
                f"project={project.uuid} vtex_account={vtex_account}"
            )
            response = self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                vtex_account=vtex_account,
                method="GET",
                path=VTEX_ACCOUNT_STORES_PATH,
            )
        except Exception as exc:
            logger.error(
                f"[VTEX_SUB_ACCOUNTS] fetch_failed: "
                f"project={project.uuid} vtex_account={vtex_account} error={exc}"
            )
            return None

        sub_accounts = self._parse_account_names(response)
        if sub_accounts is None:
            logger.warning(
                f"[VTEX_SUB_ACCOUNTS] unexpected_response: "
                f"project={project.uuid} vtex_account={vtex_account}"
            )
            return None

        logger.info(
            f"[VTEX_SUB_ACCOUNTS] resolved: "
            f"project={project.uuid} vtex_account={vtex_account} "
            f"account_count={len(sub_accounts)} "
            f"has_multiple={len(sub_accounts) > 1}"
        )
        return sub_accounts

    def _parse_account_names(self, response: Any) -> Optional[List[str]]:
        if not isinstance(response, list):
            return None

        names: List[str] = []
        for item in response:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if isinstance(name, str) and name:
                names.append(name)
        return names

    def _persist(self, project: Project, result: VtexSubAccountsSyncResult) -> None:
        config = dict(project.config or {})
        vtex_config = dict(config.get(VTEX_CONFIG_KEY) or {})
        vtex_config.pop("has_multiple_vtex_accounts", None)
        vtex_config.pop(LEGACY_VTEX_STORES_KEY, None)
        vtex_config[VTEX_SUB_ACCOUNTS_KEY] = list(result.sub_accounts)
        config[VTEX_CONFIG_KEY] = vtex_config
        project.config = config
        project.save(update_fields=["config"])
