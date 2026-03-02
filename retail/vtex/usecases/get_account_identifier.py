from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.base import BaseVtexUseCase


class GetAccountIdentifierUsecase(BaseVtexUseCase):
    """
    Use case to retrieve the VTEX account identifier
    for a given project based on its UUID.
    """

    def __init__(self, vtex_io_service: VtexIOService):
        """
        Initialize the use case with VTEX IO service.

        Args:
            vtex_io_service (VtexIOService): The service instance for VTEX IO API access.
        """
        self.vtex_io_service = vtex_io_service

    def execute(self, project_uuid: str) -> dict:
        """
        Executes the account identifier lookup by resolving the account domain.

        Args:
            project_uuid (str): UUID of the project linked to the VTEX account.

        Returns:
            dict: Response from VTEX IO containing the account identifier information.
        """
        vtex_account, account_domain = self._get_vtex_context(project_uuid)
        return self.vtex_io_service.get_account_identifier(
            account_domain=account_domain,
            vtex_account=vtex_account,
        )
