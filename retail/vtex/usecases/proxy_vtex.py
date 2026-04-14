import logging
from typing import Union

import sentry_sdk
from rest_framework.exceptions import ValidationError

from retail.clients.exceptions import CustomAPIException
from retail.services.vtex_io.service import VtexIOService
from retail.vtex.usecases.base import BaseVtexUseCase

logger = logging.getLogger(__name__)


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

        Raises:
            ValidationError: When the project or VTEX account context is invalid.
            CustomAPIException: When the upstream VTEX IO request fails.
        """
        try:
            vtex_account, account_domain = self._get_vtex_context(project_uuid)
        except ValueError as exc:
            logger.error(f"VTEX context error for project_uuid={project_uuid}: {exc}")
            raise ValidationError({"detail": str(exc)}) from exc

        logger.info(
            f"Proxying VTEX request: method={method} path={path} "
            f"project_uuid={project_uuid} vtex_account={vtex_account}"
        )

        try:
            return self.vtex_io_service.proxy_vtex(
                account_domain=account_domain,
                vtex_account=vtex_account,
                method=method,
                path=path,
                headers=headers,
                data=data,
                params=params,
            )
        except CustomAPIException:
            logger.error(
                f"VTEX IO proxy error: method={method} path={path} "
                f"project_uuid={project_uuid} vtex_account={vtex_account}"
            )
            raise
        except Exception as exc:
            logger.error(
                f"Unexpected error proxying VTEX: method={method} path={path} "
                f"project_uuid={project_uuid} vtex_account={vtex_account}: {exc}",
                exc_info=True,
            )
            sentry_sdk.capture_exception(exc)
            raise CustomAPIException(
                detail=f"Unexpected proxy error: {exc}",
                status_code=502,
            ) from exc
