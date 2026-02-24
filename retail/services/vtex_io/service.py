from retail.interfaces.clients.vtex_io.interface import VtexIOClientInterface
from retail.clients.vtex_io.client import VtexIOClient


class VtexIOService:
    """
    Service for interacting with VTEX IO APIs.
    Provides methods to fetch order form details and order history based on email.
    All methods use JWT authentication for secure inter-module communication.
    """

    def __init__(self, client: VtexIOClientInterface = None):
        """
        Initialize the VTEX IO service with the provided client.

        Args:
            client (VtexIOClientInterface): The client interface for VTEX IO.
        """
        self.client = client or VtexIOClient()

    def get_order_form_details(
        self, account_domain: str, vtex_account: str, order_form_id: str
    ) -> dict:
        """
        Retrieve order form details from VTEX IO.

        Args:
            account_domain (str): The domain of the VTEX account.
            vtex_account (str): VTEX account for JWT token generation.
            order_form_id (str): The unique identifier of the order form.

        Returns:
            dict: The order form details if successful
        """
        return self.client.get_order_form_details(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_form_id=order_form_id,
        )

    def get_order_details(
        self, account_domain: str, vtex_account: str, user_email: str
    ) -> dict:
        """
        Retrieve order details by user email from VTEX IO.

        Args:
            account_domain (str): The domain of the VTEX account.
            vtex_account (str): VTEX account for JWT token generation.
            user_email (str): The email address of the user.

        Returns:
            dict: The order details if successful
        """
        return self.client.get_order_details(
            account_domain=account_domain,
            vtex_account=vtex_account,
            user_email=user_email,
        )

    def get_order_details_by_id(
        self, account_domain: str, vtex_account: str, order_id: str
    ) -> dict:
        """
        Retrieve order details by order ID from VTEX IO.

        Args:
            account_domain (str): The domain of the VTEX account.
            vtex_account (str): VTEX account for JWT token generation.
            order_id (str): The order ID to fetch details for.

        Returns:
            dict: The order details if successful
        """
        return self.client.get_order_details_by_id(
            account_domain=account_domain,
            vtex_account=vtex_account,
            order_id=order_id,
        )

    def get_orders(
        self, account_domain: str, vtex_account: str, query_params: str
    ) -> dict:
        """
        Retrieve orders from VTEX IO.

        Args:
            account_domain (str): The domain of the VTEX account.
            vtex_account (str): VTEX account for JWT token generation.
            query_params (str): The query parameters to filter orders.

        Returns:
            dict: The orders if successful
        """
        return self.client.get_orders(
            account_domain=account_domain,
            vtex_account=vtex_account,
            query_params=query_params,
        )

    def get_account_identifier(self, account_domain: str, vtex_account: str) -> dict:
        """
        Retrieve account identifier from VTEX IO.

        Args:
            account_domain (str): The domain of the VTEX account.
            vtex_account (str): VTEX account for JWT token generation.

        Returns:
            dict: The account identifier if successful
        """
        return self.client.get_account_identifier(
            account_domain=account_domain,
            vtex_account=vtex_account,
        )

    def proxy_vtex(
        self,
        account_domain: str,
        vtex_account: str,
        method: str,
        path: str,
        headers: dict = None,
        data: dict = None,
        params: dict = None,
    ) -> dict:
        """
        Acts as a generic proxy to VTEX IO API endpoints.

        Args:
            account_domain (str): The domain of the VTEX account.
            vtex_account (str): VTEX account for JWT token generation.
            method (str): HTTP method (GET, POST, PUT, PATCH).
            path (str): API endpoint path.
            headers (dict, optional): Additional headers to be sent with the request.
            data (dict, optional): Request body data for POST, PUT, PATCH requests.
            params (dict, optional): Query parameters to be appended to the URL.

        Returns:
            dict: Response data from VTEX platform.
        """
        return self.client.proxy_vtex(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method=method,
            path=path,
            headers=headers,
            data=data,
            params=params,
        )
