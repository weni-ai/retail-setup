from retail.interfaces.clients.vtex_io.interface import VtexIOClientInterface


class VtexIOService:
    """
    Service for interacting with VTEX IO APIs.
    Provides methods to fetch order form details and order history based on email.
    """

    def __init__(self, client: VtexIOClientInterface):
        """
        Initialize the VTEX IO service with the provided client.

        Args:
            client (VtexIOClientInterface): The client interface for VTEX IO.
        """
        self.client = client

    def get_order_form_details(self, account_domain: str, order_form_id: str) -> dict:
        """
        Retrieve order form details from VTEX IO.

        Args:
            account_domain (str): The domain of the VTEX account.
            order_form_id (str): The unique identifier of the order form.

        Returns:
            dict: The order form details if successful

        """
        return self.client.get_order_form_details(account_domain, order_form_id)

    def get_order_details(self, account_domain: str, user_email: str) -> dict:
        """
        Retrieve order details by user email from VTEX IO.

        Args:
            account_domain (str): The domain of the VTEX account.
            user_email (str): The email address of the user.

        Returns:
            dict: The order details if successful

        """

        return self.client.get_order_details(account_domain, user_email)