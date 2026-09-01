from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.weni_mixins import WeniAuthMixin
from retail.webhooks.vtex.serializers import BackInStockNotificationSerializer
from retail.webhooks.vtex.usecases.dto import (
    EnqueueBackInStockNotificationsDTO,
    ProcessBackInStockNotificationDTO,
)
from retail.webhooks.vtex.usecases.enqueue_back_in_stock_notifications import (
    EnqueueBackInStockNotificationsUseCase,
)


NOTIFICATION_RECEIVED = "Notification received."


class BackInStockNotification(WeniAuthMixin, APIView):
    """Accept a back-in-stock batch from VTEX IO.

    Validates the body and delegates enqueue to the use case. The HTTP
    200 only means the batch was accepted, not that WhatsApp was sent.
    Tenant (``vtex_account``) comes from ``self.auth``.
    """

    def post(self, request: Request) -> Response:
        serializer = BackInStockNotificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data
        dto = EnqueueBackInStockNotificationsDTO(
            account=self.auth.vtex_account,
            shoppers=tuple(
                ProcessBackInStockNotificationDTO(
                    sku_id=validated_data["sku_id"],
                    phone=shopper["phone"],
                    name=shopper["name"],
                    locale=shopper["locale"],
                )
                for shopper in validated_data["shoppers"]
            ),
        )
        EnqueueBackInStockNotificationsUseCase().execute(dto)
        return Response(
            {"message": NOTIFICATION_RECEIVED},
            status=status.HTTP_200_OK,
        )
