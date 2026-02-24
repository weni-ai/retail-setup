from abc import ABC, abstractmethod


class VtexIOClientInterface(ABC):
    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
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
        pass

    @abstractmethod
    def get_orders(
        self, account_domain: str, vtex_account: str, query_params: str
    ) -> dict:
        """
        Acts as a proxy to fetch orders from VTEX IO OMS API.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            query_params (str): Query parameters to filter orders.

        Returns:
            dict: Orders data from VTEX IO.
        """
        pass

    @abstractmethod
    def get_account_identifier(self, account_domain: str, vtex_account: str) -> dict:
        """
        Retrieves the VTEX account identifier.

        Args:
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.

        Returns:
            dict: Account identifier details.
        """
        pass

    @abstractmethod
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
            account_domain (str): VTEX account domain.
            vtex_account (str): VTEX account for JWT token generation.
            method (str): HTTP method (GET, POST, PUT, PATCH).
            path (str): API endpoint path.
            headers (dict, optional): Additional headers to be sent with the request.
            data (dict, optional): Request body data for POST, PUT, PATCH requests.
            params (dict, optional): Query parameters to be appended to the URL.

        Returns:
            dict: Response data from VTEX platform.
        """
        pass
