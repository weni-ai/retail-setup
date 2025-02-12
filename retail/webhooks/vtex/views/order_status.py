from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.webhooks.vtex.serializers import OrderStatusSerializer
from retail.webhooks.vtex.usecases.order_status import OrderStatusUseCase
from retail.webhooks.vtex.usecases.typing import OrderStatusDTO


class OrderStatusWebhook(APIView):
    permission_classes = [CanCommunicateInternally]

    def post(self, request: Request) -> Response:
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = OrderStatusDTO(**serializer.validated_data)

        OrderStatusUseCase(validated_data).process_notification()

        return Response(
            {
                "message": "Order status processed successfully",
                "order_id": validated_data.orderId,
            },
            status=status.HTTP_200_OK,
        )
