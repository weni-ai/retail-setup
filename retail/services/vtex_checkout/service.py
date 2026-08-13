"""Thin wrapper around VTEX Checkout API calls via the IO proxy.

Each method catches infrastructure errors, logs with ``vtex_account``
context, and returns ``None`` so the calling use case can decide whether
to abort or continue best-effort.
"""

import logging
from typing import Any, Dict, List, Optional, Union

from retail.clients.exceptions import CustomAPIException
from retail.services.vtex_io.service import VtexIOService

logger = logging.getLogger(__name__)


class VtexCheckoutService:
    def __init__(self, vtex_io_service: Optional[VtexIOService] = None):
        self.vtex_io_service = vtex_io_service or VtexIOService()

    def get_order_form(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
    ) -> Optional[Dict[str, Any]]:
        return self._proxy(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method="GET",
            path=f"/api/checkout/pub/orderForm/{order_form_id}",
            operation="get_order_form",
        )

    def create_cart(
        self,
        account_domain: str,
        vtex_account: str,
        sales_channel: Optional[Union[str, int]] = None,
    ) -> Optional[Dict[str, Any]]:
        params: Dict[str, Any] = {"forceNewCart": "true"}
        if sales_channel is not None and sales_channel != "":
            params["sc"] = sales_channel

        return self._proxy(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method="GET",
            path="/api/checkout/pub/orderForm",
            params=params,
            operation="create_cart",
        )

    def add_items(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
        order_items: List[Dict[str, Any]],
    ) -> Optional[Dict[str, Any]]:
        return self._proxy(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method="PATCH",
            path=f"/api/checkout/pub/orderForm/{order_form_id}/items",
            data={"orderItems": order_items},
            operation="add_items",
        )

    def set_client_profile_data(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
        client_profile_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._proxy(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method="POST",
            path=(
                f"/api/checkout/pub/orderForm/{order_form_id}"
                "/attachments/clientProfileData"
            ),
            data=client_profile_data,
            operation="set_client_profile_data",
        )

    def set_shipping_data(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
        shipping_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._proxy(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method="POST",
            path=(
                f"/api/checkout/pub/orderForm/{order_form_id}"
                "/attachments/shippingData"
            ),
            data=shipping_data,
            operation="set_shipping_data",
        )

    def set_client_preferences_data(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
        client_preferences_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._proxy(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method="POST",
            path=(
                f"/api/checkout/pub/orderForm/{order_form_id}"
                "/attachments/clientPreferencesData"
            ),
            data=client_preferences_data,
            operation="set_client_preferences_data",
        )

    def set_marketing_data(
        self,
        account_domain: str,
        vtex_account: str,
        order_form_id: str,
        marketing_data: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        return self._proxy(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method="POST",
            path=(
                f"/api/checkout/pub/orderForm/{order_form_id}"
                "/attachments/marketingData"
            ),
            data=marketing_data,
            operation="set_marketing_data",
        )

    def _proxy(
        self,
        account_domain: str,
        vtex_account: str,
        method: str,
        path: str,
        operation: str,
        data: Union[dict, list, None] = None,
        params: Optional[dict] = None,
    ) -> Optional[Dict[str, Any]]:
        try:
            return self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                vtex_account=vtex_account,
                method=method,
                path=path,
                data=data,
                params=params,
            )
        except CustomAPIException as exc:
            logger.error(
                f"VTEX Checkout {operation} failed for vtex_account={vtex_account} "
                f"path={path}: status={exc.status_code} detail={exc.detail}"
            )
            return None
        except Exception as exc:
            logger.error(
                f"Unexpected error in VTEX Checkout {operation} for "
                f"vtex_account={vtex_account} path={path}: {exc}",
                exc_info=True,
            )
            return None
