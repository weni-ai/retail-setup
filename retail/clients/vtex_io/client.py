"""Client for connection with Vtex IO"""

from typing import Optional

from django.conf import settings

from retail.clients.base import RequestClient
from retail.interfaces.clients.vtex_io.interface import VtexIOClientInterface
from retail.jwt_keys.usecases.generate_jwt import JWTUsecase


JWT_EXPIRATION_MINUTES = 1


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

    def _get_jwt_headers(self, project_uuid: str) -> dict:
        """
        Generates headers with JWT authentication for inter-module communication.

        Args:
            project_uuid: The project UUID to include in the JWT token.

        Returns:
            dict: Headers with X-Weni-Auth JWT token.
        """
        token = self.jwt_usecase.generate_jwt_token(
            project_uuid=project_uuid,
            expiration_minutes=JWT_EXPIRATION_MINUTES,
        )
        return {
            "Content-Type": "application/json; charset: utf-8",
            "X-Weni-Auth": token,
        }

    def get_order_form_details(
        self, account_domain: str, project_uuid: str, order_form_id: str
    ) -> dict:
        """
        Fetches order form details by ID.

        Args:
            account_domain (str): VTEX account domain.
            project_uuid (str): Project UUID for JWT token generation.
            order_form_id (str): Unique identifier for the order form.

        Returns:
            dict: Order form details.
        """
        url = self._get_url(account_domain, "/order-form-details")
        params = {
            "orderFormId": order_form_id,
        }
        headers = self._get_jwt_headers(project_uuid)
        response = self.make_request(url, method="GET", params=params, headers=headers)

        return response.json()

    def get_order_details(
        self, account_domain: str, project_uuid: str, user_email: str
    ) -> dict:
        """
        Fetches order details by user email.

        Args:
            account_domain (str): VTEX account domain.
            project_uuid (str): Project UUID for JWT token generation.
            user_email (str): Email address of the user.

        Returns:
            dict: Order details.
        """
        url = self._get_url(account_domain, "/orders-by-email")
        params = {
            "user_email": user_email,
        }
        headers = self._get_jwt_headers(project_uuid)
        response = self.make_request(url, method="GET", params=params, headers=headers)

        return response.json()

    def get_order_details_by_id(
        self, account_domain: str, project_uuid: str, order_id: str
    ) -> dict:
        """
        Fetches order details by order ID.

        Args:
            account_domain (str): VTEX account domain.
            project_uuid (str): Project UUID for JWT token generation.
            order_id (str): The order ID to fetch details for.

        Returns:
            dict: Order details.
        """
        url = self._get_url(account_domain, "/order-by-id")
        params = {
            "orderId": order_id,
        }
        headers = self._get_jwt_headers(project_uuid)
        response = self.make_request(url, method="GET", params=params, headers=headers)

        return response.json()

    def get_orders(
        self, account_domain: str, project_uuid: str, query_params: str
    ) -> dict:
        """
        Acts as a proxy to fetch orders from VTEX IO OMS API.

        This method forwards the query parameters to the VTEX IO API
        and returns the response.

        Args:
            account_domain (str): VTEX account domain.
            project_uuid (str): Project UUID for JWT token generation.
            query_params (str): Query parameters to filter orders.

        Returns:
            dict: Orders data from VTEX IO.
        """
        url = self._get_url(account_domain, "/get-orders")

        data = {
            "raw_query": query_params,
        }
        headers = self._get_jwt_headers(project_uuid)
        response = self.make_request(url, method="POST", json=data, headers=headers)

        return response.json()

    def get_account_identifier(self, account_domain: str, project_uuid: str) -> dict:
        """
        Retrieves the VTEX account identifier.

        Args:
            account_domain (str): VTEX account domain.
            project_uuid (str): Project UUID for JWT token generation.

        Returns:
            dict: Account identifier details.
        """
        url = self._get_url(account_domain, "/account-identifier")
        headers = self._get_jwt_headers(project_uuid)
        response = self.make_request(url, method="GET", headers=headers)
        return response.json()

    def proxy_vtex(
        self,
        account_domain: str,
        project_uuid: str,
        method: str,
        path: str,
        headers: dict = None,
        data: dict = None,
        params: dict = None,
    ) -> dict:
        """
        Acts as a generic proxy to VTEX IO API endpoints.

        This method forwards requests to the VTEX IO proxy endpoint and returns
        the response from the VTEX platform. Uses JWT authentication for
        secure inter-module communication.

        Args:
            account_domain (str): VTEX account domain.
            project_uuid (str): Project UUID for JWT token generation.
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
                project_uuid="550e8400-e29b-41d4-a716-446655440000",
                method="GET",
                path="/api/oms/pvt/orders",
                params={"f_Status": "ready-for-handling"}
            )

            # Post data with custom headers
            response = client.proxy_vtex(
                account_domain="recorrenciacharlie.myvtex.com",
                project_uuid="550e8400-e29b-41d4-a716-446655440000",
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

        jwt_headers = self._get_jwt_headers(project_uuid)
        response = self.make_request(
            url, method="POST", json=payload, headers=jwt_headers
        )

        return response.json()
