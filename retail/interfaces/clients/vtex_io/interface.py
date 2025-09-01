from abc import ABC, abstractmethod


class VtexIOClientInterface(ABC):
    @abstractmethod
    def get_order_form_details(self, account_domain: str, order_form_id: str) -> dict:
        pass

    @abstractmethod
    def get_order_details(self, account_domain: str, user_email: str) -> dict:
        pass

    @abstractmethod
    def get_order_details_by_id(self, account_domain: str, order_id: str) -> dict:
        pass

    @abstractmethod
    def get_orders(self, account_domain: str, query: str) -> dict:
        pass

    @abstractmethod
    def get_account_identifier(self, account_domain: str) -> dict:
        """
        Retrieves the VTEX account identifier.

        Args:
            account_domain (str): VTEX account domain.

        Returns:
            dict: Account identifier details.
        """
        pass

    @abstractmethod
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

        Args:
            account_domain (str): VTEX account domain.
            method (str): HTTP method (GET, POST, PUT, PATCH).
            path (str): API endpoint path.
            headers (dict, optional): Additional headers to be sent with the request.
            data (dict, optional): Request body data for POST, PUT, PATCH requests.
            params (dict, optional): Query parameters to be appended to the URL.

        Returns:
            dict: Response data from VTEX platform.
        """
        pass
