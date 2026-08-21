"""Resolve the VTEX sub-account that originated an order."""

import logging
from typing import Optional

from django.core.cache import cache

from retail.projects.models import Project
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.sub_accounts import (
    ORDER_ORIGIN_CACHE_KEY_PREFIX,
    ORDER_ORIGIN_CACHE_TIMEOUT_SECONDS,
    origin_account_from_hostname,
    read_vtex_sub_accounts,
)

logger = logging.getLogger(__name__)


class ResolveOrderOriginAccountUseCase:
    """Read OMS ``hostname`` using the account that received the webhook."""

    def __init__(self, vtex_io_service: Optional[VtexIOService] = None):
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def execute(
        self,
        order_id: str,
        ingress_vtex_account: str,
        ingress_project: Optional[Project] = None,
    ) -> Optional[str]:
        """Return the origin sub-account name for ``order_id``, or None on failure.

        Args:
            order_id: VTEX order id from the webhook.
            ingress_vtex_account: Account that received the webhook.
            ingress_project: Project of that account, used to map hostname
                to a persisted sub-account name.
        """
        if not order_id or not ingress_vtex_account:
            return None

        cache_key = f"{ORDER_ORIGIN_CACHE_KEY_PREFIX}_{ingress_vtex_account}_{order_id}"
        cached = cache.get(cache_key)
        if cached:
            return cached

        hostname = self._fetch_hostname(order_id, ingress_vtex_account)
        if not hostname:
            return None

        account_names = (
            read_vtex_sub_accounts(ingress_project)
            if ingress_project is not None
            else []
        )
        origin_account = origin_account_from_hostname(hostname, account_names)

        cache.set(cache_key, origin_account, timeout=ORDER_ORIGIN_CACHE_TIMEOUT_SECONDS)
        logger.info(
            f"[ORDER_STATUS] order_origin_resolved: order_id={order_id} "
            f"ingress_account={ingress_vtex_account} hostname={hostname} "
            f"origin_account={origin_account}"
        )
        return origin_account

    def _fetch_hostname(
        self, order_id: str, ingress_vtex_account: str
    ) -> Optional[str]:
        account_domain = f"{ingress_vtex_account}.myvtex.com"
        path = f"/api/oms/pvt/orders/{order_id}"
        try:
            response = self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                vtex_account=ingress_vtex_account,
                method="GET",
                path=path,
            )
        except Exception as exc:
            logger.warning(
                f"[ORDER_STATUS] order_origin_lookup_failed: "
                f"ingress_account={ingress_vtex_account} order_id={order_id} "
                f"error={exc}"
            )
            return None

        if not isinstance(response, dict):
            logger.warning(
                f"[ORDER_STATUS] order_origin_unexpected_response: "
                f"ingress_account={ingress_vtex_account} order_id={order_id}"
            )
            return None

        hostname = response.get("hostname")
        if not isinstance(hostname, str) or not hostname.strip():
            logger.warning(
                f"[ORDER_STATUS] order_origin_missing_hostname: "
                f"ingress_account={ingress_vtex_account} order_id={order_id}"
            )
            return None
        return hostname.strip()
