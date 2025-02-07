from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.features.models import IntegratedFeature
from retail.internal.permissions import CanCommunicateInternally
from retail.projects.models import Project
from retail.webhooks.vtex.serializers import OrderStatusSerializer
from retail.webhooks.vtex.usecases.order_status import OrderStatusUseCase


class OrderStatusWebhook(APIView):
    permission_classes = [CanCommunicateInternally]

    def post(self, request: Request) -> Response:
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        validated_data = serializer.validated_data

        vtex_account = validated_data.get("vtexAccount")

        domain = OrderStatusUseCase.get_domain_by_account(vtex_account)
        project = Project.objects.get(vtex_account=vtex_account)
        integrated_feature = IntegratedFeature.objects.get(
            project=project,
            feature__code="order_status",
        )

        # TODO: process data

        return Response(
            {
                "message": "Order status processed successfully",
                "order_id": validated_data.get("orderId"),
            },
            status=status.HTTP_200_OK,
        )
