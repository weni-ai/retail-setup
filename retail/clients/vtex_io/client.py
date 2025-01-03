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


class VtexIOClient(RequestClient, VtexIOClientInterface):
    """
    Handles API communication with VTEX IO.
    """

    def __init__(self):
        """
        Initializes the authentication instance.
        """
        self.authentication_instance = InternalVtexIOAuthentication()

    def get_order_form_details(self, account_domain: str, order_form_id: str) -> dict:
        """
        Fetches order form details by ID.

        Args:
            account_domain (str): VTEX account domain.
            order_form_id (str): Unique identifier for the order form.

        Returns:
            dict: Order form details.
        """
        url = f"https://{account_domain}/_v/order-form-details"
        params = {
            "orderFormId": order_form_id,
            "token": self.authentication_instance.token,
        }
        response = self.make_request(url, method="GET", params=params)

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
        url = f"https://{account_domain}/_v/orders-by-email"
        params = {
            "user_email": user_email,
            "token": self.authentication_instance.token,
        }
        response = self.make_request(url, method="GET", params=params)

        return response.json()
