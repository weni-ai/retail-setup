from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.vtex.tasks import task_order_status_update
from retail.webhooks.vtex.serializers import OrderStatusSerializer


class OrderStatusWebhook(APIView):
    permission_classes = [CanCommunicateInternally]

    def post(self, request: Request) -> Response:
        """
        Handle incoming order status updates and trigger asynchronous processing.
        """
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        task_order_status_update.apply_async(
            args=[validated_data], queue="vtex-io-orders-update-events"
        )
        return Response(
            {
                "message": "Order status processing has been queued.",
                "order_id": validated_data["orderId"],
            },
            status=status.HTTP_202_ACCEPTED,
        )
