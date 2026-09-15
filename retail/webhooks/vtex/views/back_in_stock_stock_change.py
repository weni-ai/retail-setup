import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.weni_mixins import WeniAuthMixin
from retail.webhooks.vtex.serializers import BackInStockStockChangeSerializer
from retail.webhooks.vtex.usecases.dto import BackInStockStockChangeDTO
from retail.webhooks.vtex.usecases.handle_back_in_stock_stock_change import (
    HandleBackInStockStockChangeUseCase,
)


logger = logging.getLogger(__name__)


class BackInStockStockChange(WeniAuthMixin, APIView):
    """Accept a catalog stock-change from VTEX IO.

    Only SISMEMBER (or rebuild-on-missing) happens in this request. The account
    in the URL identifies the store in access logs and dashboards; the tenant
    itself comes from ``self.auth``.
    """

    def post(self, request: Request, vtex_account: str) -> Response:
        account = self.auth.vtex_account
        logger.info(f"[BACK_IN_STOCK] Processing stock change: vtex_account={account}")

        serializer = BackInStockStockChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = HandleBackInStockStockChangeUseCase().execute(
            BackInStockStockChangeDTO(
                account=account,
                sku_id=serializer.validated_data["sku_id"],
            )
        )
        return Response(result.to_dict(), status=status.HTTP_200_OK)
