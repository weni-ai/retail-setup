class MerchantAccountNotAllowedError(Exception):
    """Raised when merchant_name is not a seller of the project's VTEX account."""

    def __init__(self, merchant_name: str, project_account: str):
        self.merchant_name = merchant_name
        self.project_account = project_account
        super().__init__(
            f"merchant_name={merchant_name} is not a seller of {project_account}"
        )
