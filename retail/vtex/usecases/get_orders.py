from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.base import BaseVtexUseCase


class GetOrdersUsecase(BaseVtexUseCase):
    def __init__(self, vtex_io_service: VtexIOService):
        self.vtex_io_service = vtex_io_service

    def execute(self, data: dict, project_uuid: str) -> dict:
        """
        Execute the get orders use case.

        Args:
            params (dict): Parameters containing project_uuid and other query parameters

        Returns:
            dict: Orders data from VTEX IO
        """
        # Remove project_uuid from params as it's not needed for the VTEX API call
        raw_query = data.get("raw_query")
        account_domain = self._get_account_domain(project_uuid)
        return self.vtex_io_service.get_orders(
            account_domain=account_domain, query_params=raw_query
        )
