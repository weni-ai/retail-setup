import logging

from retail.services.vtex_io.service import VtexIOService
from retail.vtex.dtos.proxy_payment_gateway_dto import ProxyPaymentGatewayDTO
from retail.vtex.usecases.base import BaseVtexUseCase

logger = logging.getLogger(__name__)


class ProxyPaymentGatewayUseCase(BaseVtexUseCase):
    """
    Use case for proxying requests to the VTEX IO Payment Gateway
    proxy route (/_v/proxy-payment-gateway).
    """

    def __init__(self, vtex_io_service: VtexIOService):
        self.vtex_io_service = vtex_io_service

    def execute(self, dto: ProxyPaymentGatewayDTO, project_uuid: str) -> dict:
        """
        Forwards a Payment Gateway request to VTEX IO.

        Args:
            dto: Validated proxy request data.
            project_uuid: Project UUID to resolve VTEX context.

        Returns:
            dict: Response from the VTEX IO proxy-payment-gateway route.
        """
        vtex_account, account_domain = self._get_vtex_context(project_uuid)

        logger.info(
            f"Proxying payment gateway request for "
            f"vtex_account={vtex_account} method={dto.method} path={dto.path}"
        )

        return self.vtex_io_service.proxy_payment_gateway(
            account_domain=account_domain,
            vtex_account=vtex_account,
            method=dto.method,
            path=dto.path,
            headers=dto.headers,
            data=dto.data,
            params=dto.params,
        )
