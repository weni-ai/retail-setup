from typing import Union

from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.base import BaseVtexUseCase


class ProxyVtexUsecase(BaseVtexUseCase):
    """
    Use case for proxying requests to VTEX IO API endpoints.
    """

    def __init__(self, vtex_io_service: VtexIOService):
        """
        Initialize the proxy VTEX use case.

        Args:
            vtex_io_service (VtexIOService): The VTEX IO service instance.
        """
        self.vtex_io_service = vtex_io_service

    def execute(
        self,
        method: str,
        path: str,
        headers: dict = None,
        data: Union[dict, list] = None,
        params: dict = None,
        project_uuid: str = None,
    ) -> dict:
        """
        Execute the proxy VTEX use case.

        Args:
            method (str): HTTP method (GET, POST, PUT, PATCH).
            path (str): API endpoint path.
            headers (dict, optional): Additional headers to be sent with the request.
            data (Union[dict, list], optional): Request body data for POST, PUT, PATCH requests.
            params (dict, optional): Query parameters to be appended to the URL.
            project_uuid (str): Project UUID to get the account domain.

        Returns:
            dict: Response data from VTEX platform.
        """
        vtex_account, account_domain = self._get_vtex_context(project_uuid)
        return self.vtex_io_service.proxy_vtex(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method=method,
            path=path,
            headers=headers,
            data=data,
            params=params,
        )
