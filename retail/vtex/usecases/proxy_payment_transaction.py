import logging

from retail.services.vtex_io.service import VtexIOService
from retail.vtex.dtos.proxy_payment_transaction_dto import ProxyPaymentTransactionDTO
from retail.vtex.usecases.base import BaseVtexUseCase

logger = logging.getLogger(__name__)


class ProxyPaymentTransactionUseCase(BaseVtexUseCase):
    """
    Use case for proxying payment transaction requests to the VTEX IO
    agentic-cx proxy-payment-transaction route.
    """

    def __init__(self, vtex_io_service: VtexIOService):
        self.vtex_io_service = vtex_io_service

    def execute(self, dto: ProxyPaymentTransactionDTO, project_uuid: str) -> dict:
        """
        Forwards a payment transaction to VTEX IO.

        Args:
            dto: Validated payment transaction data.
            project_uuid: Project UUID to resolve VTEX context.

        Returns:
            dict: Response from the VTEX IO proxy-payment-transaction route.
        """
        vtex_account, account_domain = self._get_vtex_context(project_uuid)

        logger.info(
            f"Proxying payment transaction for "
            f"vtex_account={vtex_account} transaction_id={dto.transaction_id}"
        )

        return self.vtex_io_service.proxy_payment_transaction(
            account_domain=account_domain,
            vtex_account=vtex_account,
            transaction_id=dto.transaction_id,
            payments=list(dto.payments),
        )
