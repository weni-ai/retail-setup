class OrderStatusUseCase:
    """
    Use case for handling order status updates.
    """

    @classmethod
    def get_domain_by_account(cls, account: str) -> str:
        """
        Get the domain for a given account.
        """
        return f"https://{account}.vtexcommercestable.com.br"
