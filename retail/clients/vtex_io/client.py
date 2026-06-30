"""Client for connection with Vtex IO"""

import logging
from typing import Optional, Union

from django.conf import settings

from retail.clients.base import RequestClient
from retail.clients.exceptions import CustomAPIException
from retail.interfaces.clients.vtex_io.interface import VtexIOClientInterface
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase
from retail.observability.sentry import (
    fingerprint_with_vtex_account,
    sentry_error_scope,
)
from retail.observability.vtex_io import build_vtex_io_proxy_sentry_metadata


logger = logging.getLogger(__name__)


JWT_EXPIRATION_MINUTES = 1

VTEX_IO_PROXY_SERVICE = "vtex_io_proxy"
VTEX_IO_PROXY_PAYMENT_GATEWAY_SERVICE = "vtex_io_proxy_payment_gateway"
VTEX_IO_PROXY_PAYMENT_TRANSACTION_SERVICE = "vtex_io_proxy_payment_transaction"


class VtexIOClient(RequestClient, VtexIOClientInterface):
    """
    Handles API communication with VTEX IO using JWT authentication.
    """

    def __init__(self, jwt_usecase: Optional[JWTUsecase] = None):
        """
        Initializes the JWT usecase for authentication.

        Args:
            jwt_usecase: Optional JWTUsecase instance for JWT token generation.
                        If not provided, a new instance will be created.
        """
        self.jwt_usecase = jwt_usecase or JWTUsecase()

    def _get_url(self, account_domain: str, path: str) -> str:
        """
        Builds the complete URL for VTEX IO API requests, optionally including a workspace prefix.

        Args:
            account_domain (str): VTEX account domain (e.g., 'wenipartnerbr.myvtex.com').
            path (str): API endpoint path (e.g., '/get-feature-list').

        Returns:
            str: Complete URL for the API request.
        """
        workspace_prefix = getattr(settings, "VTEX_IO_WORKSPACE", "")
        if workspace_prefix:
            # Example: weni--wenipartnerbr.myvtex.com
            domain = f"{workspace_prefix}--{account_domain}"
        else:
            domain = account_domain

        return f"https://{domain}/_v{path}"

    def _get_jwt_headers(self, vtex_account: str) -> dict:
        """
        Generates headers with JWT authentication for inter-module communication.

        Args:
            vtex_account: The VTEX account to include in the JWT token.

        Returns:
            dict: Headers with X-Weni-Auth JWT token.
        """
        token = self.jwt_usecase.generate_proxy_vtex_jwt_token(
            vtex_account=vtex_account,
            expiration_minutes=JWT_EXPIRATION_MINUTES,
        )
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Accept-Encoding": "identity",
            "X-Weni-Auth": token,
        }

    def _parse_proxy_json_response(
        self,
        response,
        *,
        url: str,
        vtex_account: str,
        service: str,
        method: str,
        path: str = None,
    ) -> dict:
        """Parse a successful VTEX IO proxy response body as JSON."""
        try:
            return response.json()
        except (ValueError, TypeError) as exc:
            body_preview = response.text[:500] if response.text else ""
            sentry_metadata = self._proxy_sentry_metadata(
                service=service,
                vtex_account=vtex_account,
                method=method,
                path=path,
            )
            sentry_tags = {
                **sentry_metadata["sentry_tags"],
                "error_type": "invalid_json_response",
                "http_status": response.status_code,
            }
            with sentry_error_scope(
                fingerprint=fingerprint_with_vtex_account(
                    [service, "invalid-json-response"],
                    sentry_tags,
                ),
                tags=sentry_tags,
                context={"url": url, "body_preview": body_preview},
            ):
                logger.error(
                    f"Failed to parse VTEX IO proxy response as JSON: "
                    f"url={url} status={response.status_code} body={body_preview}"
                )
            raise CustomAPIException(
                detail="VTEX IO returned a non-JSON response",
                status_code=502,
            ) from exc

    def _proxy_sentry_metadata(
        self,
        *,
        service: str,
        vtex_account: str,
        method: str,
        path: str = None,
    ) -> dict:
        return build_vtex_io_proxy_sentry_metadata(
            service=service,
            vtex_account=vtex_account,
            method=method,
            path=path,
        )

    def get_order_form_details(
        self, account_domain: str, vtex_account: str, order_form_id: str
    ) -> dict:
        """
        Fetches order form details by ID.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            order_form_id (str): Unique identifier for the order form.

        Returns:
            dict: Order form details.
        """
        url = self._get_url(account_domain, "/order-form-details")
        params = {
            "orderFormId": order_form_id,
        }
        headers = self._get_jwt_headers(vtex_account)
        response = self.make_request(url, method="GET", params=params, headers=headers)

        return response.json()

    def get_order_details(
        self, account_domain: str, vtex_account: str, user_email: str
    ) -> dict:
        """
        Fetches order details by user email.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            user_email (str): Email address of the user.

        Returns:
            dict: Order details.
        """
        url = self._get_url(account_domain, "/orders-by-email")
        params = {
            "user_email": user_email,
        }
        headers = self._get_jwt_headers(vtex_account)
        response = self.make_request(url, method="GET", params=params, headers=headers)

        return response.json()

    def get_order_details_by_id(
        self, account_domain: str, vtex_account: str, order_id: str
    ) -> dict:
        """
        Fetches order details by order ID.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            order_id (str): The order ID to fetch details for.

        Returns:
            dict: Order details.
        """
        url = self._get_url(account_domain, "/order-by-id")
        params = {
            "orderId": order_id,
        }
        headers = self._get_jwt_headers(vtex_account)
        response = self.make_request(url, method="GET", params=params, headers=headers)

        return response.json()

    def get_orders(
        self, account_domain: str, vtex_account: str, query_params: str
    ) -> dict:
        """
        Acts as a proxy to fetch orders from VTEX IO OMS API.

        This method forwards the query parameters to the VTEX IO API
        and returns the response.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            query_params (str): Query parameters to filter orders.

        Returns:
            dict: Orders data from VTEX IO.
        """
        url = self._get_url(account_domain, "/get-orders")

        data = {
            "raw_query": query_params,
        }
        headers = self._get_jwt_headers(vtex_account)
        response = self.make_request(url, method="POST", json=data, headers=headers)

        return response.json()

    def get_account_identifier(self, account_domain: str, vtex_account: str) -> dict:
        """
        Retrieves the VTEX account identifier.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.

        Returns:
            dict: Account identifier details.
        """
        url = self._get_url(account_domain, "/account-identifier")
        headers = self._get_jwt_headers(vtex_account)
        response = self.make_request(url, method="GET", headers=headers)
        return response.json()

    def activate_agentic_cx_script(
        self, account_domain: str, vtex_account: str
    ) -> dict:
        """
        Notifies the VTEX IO app that the Agentic CX script can be installed.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.

        Returns:
            dict: Response from VTEX IO.
        """
        url = self._get_url(account_domain, "/agentic-cx/settings")
        headers = self._get_jwt_headers(vtex_account)
        response = self.make_request(
            url, method="PATCH", json={"agentic_cx_script": True}, headers=headers
        )
        return response.json()

    def proxy_vtex(
        self,
        account_domain: str,
        vtex_account: str,
        method: str,
        path: str,
        headers: dict = None,
        data: Union[dict, list] = None,
        params: dict = None,
    ) -> dict:
        """
        Acts as a generic proxy to VTEX IO API endpoints.

        This method forwards requests to the VTEX IO proxy endpoint and returns
        the response from the VTEX platform. Uses JWT authentication for
        secure inter-module communication.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            method (str): HTTP method (GET, POST, PUT, PATCH).
            path (str): API endpoint path (e.g., '/api/orders/pvt/document/1557825995418-01').
            headers (dict, optional): Additional headers to be sent with the request.
            data (Union[dict, list], optional): Request body data for POST, PUT, PATCH requests.
            params (dict, optional): Query parameters to be appended to the URL.

        Returns:
            dict: Response data from VTEX platform.

        Example:
            # Get order details with query parameters
            response = client.proxy_vtex(
                account_domain="recorrenciacharlie.myvtex.com",
                vtex_account="recorrenciacharlie",
                method="GET",
                path="/api/oms/pvt/orders",
                params={"f_Status": "ready-for-handling"}
            )

            # Post data with custom headers
            response = client.proxy_vtex(
                account_domain="recorrenciacharlie.myvtex.com",
                vtex_account="recorrenciacharlie",
                method="POST",
                path="/api/orders",
                data={"customer": "john@example.com"},
                headers={"Custom-Header": "value"}
            )
        """
        url = self._get_url(account_domain, "/proxy-vtex")

        # Prepare the request payload
        payload = {
            "method": method.upper(),
            "path": path,
        }

        if headers:
            payload["headers"] = headers
        if data:
            payload["data"] = data
        if params:
            payload["params"] = params

        jwt_headers = self._get_jwt_headers(vtex_account)
        sentry_metadata = self._proxy_sentry_metadata(
            service=VTEX_IO_PROXY_SERVICE,
            vtex_account=vtex_account,
            method=method,
            path=path,
        )
        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=jwt_headers,
            **sentry_metadata,
        )

        return self._parse_proxy_json_response(
            response,
            url=url,
            vtex_account=vtex_account,
            service=VTEX_IO_PROXY_SERVICE,
            method=method,
            path=path,
        )

    def proxy_payment_gateway(
        self,
        account_domain: str,
        vtex_account: str,
        method: str,
        path: str,
        headers: dict = None,
        data: Union[dict, list] = None,
        params: dict = None,
    ) -> dict:
        """
        Proxies requests to the VTEX IO Payment Gateway proxy route.

        Forwards method, path and optional headers/params/data to the
        /_v/proxy-payment-gateway route, which calls the VTEX Payment
        Gateway API ({account}.vtexpayments.com.br).

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            method (str): HTTP method (GET, POST, PUT).
            path (str): Payment Gateway API path.
            headers (dict, optional): Additional headers.
            data (Union[dict, list], optional): Request body data.
            params (dict, optional): Query parameters.

        Returns:
            dict: Response from the VTEX IO proxy-payment-gateway route.
        """
        url = self._get_url(account_domain, "/proxy-payment-gateway")

        payload = {
            "method": method.upper(),
            "path": path,
        }

        if headers:
            payload["headers"] = headers
        if data:
            payload["data"] = data
        if params:
            payload["params"] = params

        jwt_headers = self._get_jwt_headers(vtex_account)
        sentry_metadata = self._proxy_sentry_metadata(
            service=VTEX_IO_PROXY_PAYMENT_GATEWAY_SERVICE,
            vtex_account=vtex_account,
            method=method,
            path=path,
        )
        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=jwt_headers,
            **sentry_metadata,
        )

        return self._parse_proxy_json_response(
            response,
            url=url,
            vtex_account=vtex_account,
            service=VTEX_IO_PROXY_PAYMENT_GATEWAY_SERVICE,
            method=method,
            path=path,
        )

    def proxy_payment_transaction(
        self,
        account_domain: str,
        vtex_account: str,
        transaction_id: str,
        payments: list,
    ) -> dict:
        """
        Proxies a payment transaction request to the VTEX IO agentic-cx app.

        Forwards transactionId and payments to the /_v/proxy-payment-transaction
        route, which in turn calls the VTEX Vault payments API.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            transaction_id (str): The payment transaction ID.
            payments (list): Non-empty list of payment objects.

        Returns:
            dict: Response from the VTEX IO proxy-payment-transaction route.
        """
        url = self._get_url(account_domain, "/proxy-payment-transaction")
        payload = {
            "transactionId": transaction_id,
            "payments": payments,
        }
        headers = self._get_jwt_headers(vtex_account)
        sentry_metadata = self._proxy_sentry_metadata(
            service=VTEX_IO_PROXY_PAYMENT_TRANSACTION_SERVICE,
            vtex_account=vtex_account,
            method="POST",
        )
        response = self.make_request(
            url,
            method="POST",
            json=payload,
            headers=headers,
            **sentry_metadata,
        )

        return self._parse_proxy_json_response(
            response,
            url=url,
            vtex_account=vtex_account,
            service=VTEX_IO_PROXY_PAYMENT_TRANSACTION_SERVICE,
            method="POST",
        )
