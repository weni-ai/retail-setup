import logging
import re
from typing import Optional, Tuple

from django.core.cache import cache

from retail.clients.exceptions import CustomAPIException
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.exceptions import MerchantAccountNotAllowedError
from retail.vtex.usecases.base import BaseVtexUseCase

logger = logging.getLogger(__name__)

VTEX_ACCOUNT_PATTERN = re.compile(r"^[a-z0-9]([a-z0-9-]{0,48}[a-z0-9])?$")
SELLER_REGISTER_PATH = "/api/seller-register/pvt/sellers"
MERCHANT_ACCESS_CACHE_TTL = 3600
CACHE_ALLOW = "allow"
CACHE_DENY = "deny"


class ResolveProxyContextUseCase(BaseVtexUseCase):
    """
    Resolves the VTEX account and host for proxy calls.

    JWT and host always target the same account. A merchant override is
    accepted only when seller-register on the parent account lists that
    merchant as a VTEX seller.
    """

    def __init__(self, vtex_io_service: VtexIOService):
        self.vtex_io_service = vtex_io_service

    def execute(
        self, project_uuid: str, merchant_name: Optional[str] = None
    ) -> Tuple[str, str]:
        parent_account, parent_domain = self._get_vtex_context(project_uuid)

        if self._targets_parent_account(merchant_name, parent_account):
            return parent_account, parent_domain

        if not self._is_valid_vtex_account_name(merchant_name):
            logger.warning(
                f"Rejected malformed merchant_name={merchant_name!r} "
                f"for parent_account={parent_account}"
            )
            raise MerchantAccountNotAllowedError(merchant_name, parent_account)

        cached = self._cached_decision(parent_account, merchant_name)
        if cached is False:
            raise MerchantAccountNotAllowedError(merchant_name, parent_account)
        if cached is True:
            return self._merchant_context(merchant_name)

        allowed = self._is_seller_of_parent(
            parent_account, parent_domain, merchant_name
        )
        self._store_decision(parent_account, merchant_name, allowed)
        if not allowed:
            logger.warning(
                f"Denied merchant_name={merchant_name} for "
                f"parent_account={parent_account}: not a VTEX seller"
            )
            raise MerchantAccountNotAllowedError(merchant_name, parent_account)

        logger.info(
            f"Allowed merchant_name={merchant_name} as seller of "
            f"parent_account={parent_account}"
        )
        return self._merchant_context(merchant_name)

    def _targets_parent_account(
        self, merchant_name: Optional[str], parent_account: str
    ) -> bool:
        if not merchant_name:
            return True
        return merchant_name.lower() == parent_account.lower()

    def _is_valid_vtex_account_name(self, merchant_name: str) -> bool:
        return bool(VTEX_ACCOUNT_PATTERN.fullmatch(merchant_name))

    def _merchant_context(self, merchant_name: str) -> Tuple[str, str]:
        return merchant_name, f"{merchant_name}.myvtex.com"

    def _cache_key(self, parent_account: str, merchant_name: str) -> str:
        return (
            f"proxy_merchant_allowed_{parent_account.lower()}_{merchant_name.lower()}"
        )

    def _cached_decision(
        self, parent_account: str, merchant_name: str
    ) -> Optional[bool]:
        cached = cache.get(self._cache_key(parent_account, merchant_name))
        if cached == CACHE_ALLOW:
            return True
        if cached == CACHE_DENY:
            return False
        return None

    def _store_decision(
        self, parent_account: str, merchant_name: str, allowed: bool
    ) -> None:
        cache.set(
            self._cache_key(parent_account, merchant_name),
            CACHE_ALLOW if allowed else CACHE_DENY,
            timeout=MERCHANT_ACCESS_CACHE_TTL,
        )

    def _is_seller_of_parent(
        self, parent_account: str, parent_domain: str, merchant_name: str
    ) -> bool:
        seller = self._fetch_seller_by_id(parent_account, parent_domain, merchant_name)
        if seller is not None and self._seller_matches(seller, merchant_name):
            return True

        for candidate in self._list_sellers(
            parent_account, parent_domain, merchant_name
        ):
            if self._seller_matches(candidate, merchant_name):
                return True
        return False

    def _fetch_seller_by_id(
        self, parent_account: str, parent_domain: str, merchant_name: str
    ) -> Optional[dict]:
        try:
            payload = self._proxy_parent(
                parent_account,
                parent_domain,
                path=f"{SELLER_REGISTER_PATH}/{merchant_name}",
            )
        except CustomAPIException as exc:
            if exc.status_code == 404:
                return None
            raise

        sellers = self._as_seller_list(payload)
        return sellers[0] if sellers else None

    def _list_sellers(
        self, parent_account: str, parent_domain: str, merchant_name: str
    ) -> list:
        try:
            payload = self._proxy_parent(
                parent_account,
                parent_domain,
                path=SELLER_REGISTER_PATH,
                params={"keyword": merchant_name, "from": "0", "to": "100"},
            )
        except CustomAPIException as exc:
            if exc.status_code == 404:
                return []
            raise
        return self._as_seller_list(payload)

    def _proxy_parent(
        self,
        parent_account: str,
        parent_domain: str,
        path: str,
        params: Optional[dict] = None,
    ):
        return self.vtex_io_service.proxy_vtex(
            account_domain=parent_domain,
            vtex_account=parent_account,
            method="GET",
            path=path,
            params=params,
        )

    def _as_seller_list(self, payload) -> list:
        if isinstance(payload, list):
            return [item for item in payload if isinstance(item, dict)]
        if not isinstance(payload, dict):
            return []
        for key in ("items", "data", "sellers"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return [payload]

    def _seller_matches(self, seller: dict, merchant_name: str) -> bool:
        account = seller.get("account") or seller.get("Account")
        if not isinstance(account, str):
            return False
        if account.lower() != merchant_name.lower():
            return False
        is_vtex = seller.get("isVtex", seller.get("IsVtex"))
        return is_vtex is not False
