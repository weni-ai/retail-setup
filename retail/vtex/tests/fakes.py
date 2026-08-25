"""In-memory VTEX IO client with OMS-shaped payloads.

Production code already follows ``client or VtexIOClient``. Tests inject
this fake at that seam:

    VtexIOService(client=FakeVtexIOClient(hostname="martimx"))

Responses match the subset of ``GET /api/oms/pvt/orders/{orderId}`` that
origin routing and payment-recovery amount lookup actually read.
"""

from typing import Any, Dict, List, Optional, Union

_UNSET = object()


def oms_order_payload(
    *,
    order_id: str = "v123-01",
    hostname: str = "martimx",
    value: int = 15000,
) -> Dict[str, Any]:
    """Return a faithful subset of a VTEX OMS order document."""
    return {
        "orderId": order_id,
        "hostname": hostname,
        "merchantName": hostname,
        "value": value,
        "status": "payment-pending",
        "origin": "Marketplace",
        "storePreferencesData": {"currencyCode": "MXN"},
    }


class FakeVtexIOClient:
    """Stand-in for ``VtexIOClient`` used by ``VtexIOService``."""

    def __init__(
        self,
        *,
        hostname: str = "martimx",
        order_id: str = "v123-01",
        order_value_cents: int = 15000,
        proxy_error: Optional[BaseException] = None,
        proxy_response: Any = _UNSET,
    ) -> None:
        self.hostname = hostname
        self.order_id = order_id
        self.order_value_cents = order_value_cents
        self.proxy_error = proxy_error
        self.proxy_response = proxy_response
        self.proxy_calls: List[Dict[str, Any]] = []

    def get_order_details_by_id(
        self, account_domain: str, vtex_account: str, order_id: str
    ) -> dict:
        return oms_order_payload(
            order_id=order_id,
            hostname=self.hostname,
            value=self.order_value_cents,
        )

    def proxy_vtex(
        self,
        account_domain: str,
        vtex_account: str,
        method: str,
        path: str,
        headers: dict = None,
        data: Union[dict, list] = None,
        params: dict = None,
    ) -> Any:
        self.proxy_calls.append(
            {
                "account_domain": account_domain,
                "vtex_account": vtex_account,
                "method": method,
                "path": path,
            }
        )
        if self.proxy_error is not None:
            raise self.proxy_error
        if self.proxy_response is not _UNSET:
            return self.proxy_response

        expected_path = f"/api/oms/pvt/orders/{self.order_id}"
        if path != expected_path:
            raise AssertionError(
                f"unexpected OMS path {path!r}, expected {expected_path!r}"
            )
        return oms_order_payload(
            order_id=self.order_id,
            hostname=self.hostname,
            value=self.order_value_cents,
        )
