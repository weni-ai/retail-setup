"""Client for connection with Vtex IO"""

from django.conf import settings

from retail.clients.base import RequestClient
from retail.interfaces.clients.vtex_io.interface import VtexIOClientInterface


class InternalVtexIOAuthentication(RequestClient):
    """
    Handles authentication with VTEX IO using client credentials.
    """

    def __get_module_token(self) -> str:
        """
        Retrieves the access token from the VTEX IO OIDC endpoint.
        """
        # Authentication payload
        data = {
            "client_id": settings.VTEX_IO_OIDC_RP_CLIENT_ID,
            "client_secret": settings.VTEX_IO_OIDC_RP_CLIENT_SECRET,
            "grant_type": "client_credentials",
        }
        response = self.make_request(
            url=settings.OIDC_OP_TOKEN_ENDPOINT, method="POST", data=data
        )
        # Extracts the token
        token = response.json().get("access_token")
        if not token:
            raise ValueError("Failed to retrieve access token.")

        return token

    @property
    def token(self) -> str:
        """
        Returns the access token to be used in requests.
        """
        return self.__get_module_token()

    @property
    def headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "X-Weni-Auth": f"Bearer {self.token}",
        }


class VtexIOClient(RequestClient, VtexIOClientInterface):
    """
    Handles API communication with VTEX IO.
    """

    def __init__(self):
        """
        Initializes the authentication instance.
        """
        self.authentication = InternalVtexIOAuthentication()

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

    def get_order_form_details(self, account_domain: str, order_form_id: str) -> dict:
        """
        Fetches order form details by ID.

        Args:
            account_domain (str): VTEX account domain.
            order_form_id (str): Unique identifier for the order form.

        Returns:
            dict: Order form details.
        """
        url = self._get_url(account_domain, "/order-form-details")
        params = {
            "orderFormId": order_form_id,
        }
        response = self.make_request(
            url, method="GET", params=params, headers=self.authentication.headers
        )

        return response.json()

    def get_order_details(self, account_domain: str, user_email: str) -> dict:
        """
        Fetches order details by user email.

        Args:
            account_domain (str): VTEX account domain.
            user_email (str): Email address of the user.

        Returns:
            dict: Order details.
        """
        url = self._get_url(account_domain, "/orders-by-email")
        params = {
            "user_email": user_email,
        }
        response = self.make_request(
            url, method="GET", params=params, headers=self.authentication.headers
        )

        return response.json()

    def get_order_details_by_id(self, account_domain: str, order_id: str) -> dict:
        """
        Fetches order details by order ID.
        """
        url = self._get_url(account_domain, "/order-by-id")
        params = {
            "orderId": order_id,
        }

        response = self.make_request(
            url, method="GET", params=params, headers=self.authentication.headers
        )

        return response.json()

    def get_orders(self, account_domain: str, query_params: str) -> dict:
        """
        Acts as a proxy to fetch orders from VTEX IO OMS API.

        This method forwards the query parameters to the VTEX IO API
        and returns the response.

        Args:
            account_domain (str): VTEX account domain.
            query_params (dict): Query parameters to filter orders.

        Returns:
            dict: Orders data from VTEX IO.
        """
        url = self._get_url(account_domain, "/get-orders")

        data = {
            "raw_query": query_params,
        }
        response = self.make_request(
            url, method="POST", json=data, headers=self.authentication.headers
        )

        return response.json()

    def get_account_identifier(self, account_domain: str) -> dict:
        """
        Retrieves the VTEX account identifier.
        """
        url = self._get_url(account_domain, "/account-identifier")
        response = self.make_request(
            url, method="GET", headers=self.authentication.headers
        )
        return response.json()

    def proxy_vtex(
        self,
        account_domain: str,
        method: str,
        path: str,
        headers: dict = None,
        data: dict = None,
        params: dict = None,
    ) -> dict:
        """
        Acts as a generic proxy to VTEX IO API endpoints.

        This method forwards requests to the VTEX IO proxy endpoint and returns
        the response from the VTEX platform.

        Args:
            account_domain (str): VTEX account domain.
            method (str): HTTP method (GET, POST, PUT, PATCH).
            path (str): API endpoint path (e.g., '/api/orders/pvt/document/1557825995418-01').
            headers (dict, optional): Additional headers to be sent with the request.
            data (dict, optional): Request body data for POST, PUT, PATCH requests.
            params (dict, optional): Query parameters to be appended to the URL.

        Returns:
            dict: Response data from VTEX platform.

        Example:
            # Get order details with query parameters
            response = client.proxy_vtex(
                account_domain="recorrenciacharlie.myvtex.com",
                method="GET",
                path="/api/oms/pvt/orders",
                params={"f_Status": "ready-for-handling"}
            )

            # Post data with custom headers
            response = client.proxy_vtex(
                account_domain="recorrenciacharlie.myvtex.com",
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

        response = self.make_request(
            url, method="POST", json=payload, headers=self.authentication.headers
        )

        return response.json()
