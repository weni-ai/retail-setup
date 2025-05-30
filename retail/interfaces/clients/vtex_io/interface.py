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
