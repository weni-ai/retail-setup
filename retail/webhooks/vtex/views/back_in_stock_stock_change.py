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


class BackInStockStockChange(WeniAuthMixin, APIView):
    """Accept a catalog stock-change from VTEX IO.

    Only SISMEMBER (or rebuild-on-missing) happens in this request.
    Tenant (``vtex_account``) comes from ``self.auth``.
    """

    def post(self, request: Request) -> Response:
        serializer = BackInStockStockChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = HandleBackInStockStockChangeUseCase().execute(
            BackInStockStockChangeDTO(
                account=self.auth.vtex_account,
                sku_id=serializer.validated_data["sku_id"],
            )
        )
        return Response(result.to_dict(), status=status.HTTP_200_OK)
