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
            "Authorization": f"Bearer {self.token}",
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
            path (str): API endpoint path (e.g., '_v/get-feature-list').

        Returns:
            str: Complete URL for the API request.
        """
        workspace_prefix = getattr(settings, "VTEX_IO_WORKSPACE", "")
        if workspace_prefix:
            # Example: weni--wenipartnerbr.myvtex.com
            domain = f"{workspace_prefix}--{account_domain}"
        else:
            domain = account_domain

        return f"https://{domain}/{path}"

    def get_order_form_details(self, account_domain: str, order_form_id: str) -> dict:
        """
        Fetches order form details by ID.

        Args:
            account_domain (str): VTEX account domain.
            order_form_id (str): Unique identifier for the order form.

        Returns:
            dict: Order form details.
        """
        url = self._get_url(account_domain, "_v/order-form-details")
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
        url = self._get_url(account_domain, "_v/orders-by-email")
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
        url = self._get_url(account_domain, "_v/order-by-id")
        params = {
            "orderId": order_id,
        }

        response = self.make_request(
            url, method="GET", params=params, headers=self.authentication.headers
        )

        return response.json()
