from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.weni_mixins import WeniAuthMixin
from retail.webhooks.vtex.serializers import BackInStockSubscribeSerializer
from retail.webhooks.vtex.usecases.dto import SubscribeBackInStockDTO
from retail.webhooks.vtex.usecases.exceptions import ProjectNotFoundError
from retail.webhooks.vtex.usecases.subscribe_back_in_stock import (
    SubscribeBackInStockUseCase,
)


class BackInStockSubscribe(WeniAuthMixin, APIView):
    """Accept a back-in-stock subscribe from VTEX IO.

    Tenant (``vtex_account``) comes from ``self.auth``. Redis SADD runs
    in this request before the 200.
    """

    def post(self, request: Request) -> Response:
        serializer = BackInStockSubscribeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = SubscribeBackInStockDTO(
            account=self.auth.vtex_account,
            sku_id=data["sku_id"],
            phone=data["phone"],
            name=data["name"],
            seller=data["seller"],
            sales_channel=data["sales_channel"],
            locale=data["locale"] or "pt-BR",
        )
        try:
            SubscribeBackInStockUseCase().execute(dto)
        except ProjectNotFoundError:
            return Response(
                {"message": "Project not found for the given account."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response({"accepted": True}, status=status.HTTP_200_OK)
