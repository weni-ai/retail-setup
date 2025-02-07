from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status
from rest_framework.exceptions import ValidationError
from sentry_sdk import capture_message

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

        project = Project.objects.filter(vtex_account=vtex_account).first()

        order_id = validated_data.get("orderId")

        if not project:
            error_message = f"Project not found for VTEX account {vtex_account}. Order id: {order_id}"
            capture_message(error_message)

            raise ValidationError(
                {"error": "Project not found for this VTEX account"},
                code="project_not_found",
            )

        domain = OrderStatusUseCase.get_domain_by_account(vtex_account)

        integrated_feature = IntegratedFeature.objects.filter(
            project=project,
            feature__code="order_status",
        ).first()

        if not integrated_feature:
            error_message = f"Order status integration not found for project {project.name}. Order id: {order_id}"
            capture_message(error_message)

            raise ValidationError(
                {
                    "error": "Order status integration not found for this project",
                },
                code="order_status_integration_not_found",
            )

        template_name = OrderStatusUseCase.get_template_by_order_status(
            validated_data.get("currentState"), integrated_feature
        )

        if not template_name:
            error_message = f"Template not found for order status {validated_data.get('currentState')}. Order id: {order_id}"
            capture_message(error_message)

            raise ValidationError(
                {
                    "error": "Template not found for this order status",
                },
                code="template_not_found",
            )

        OrderStatusUseCase.process_notification(
            domain, validated_data.get("orderId"), template_name
        )

        return Response(
            {
                "message": "Order status processed successfully",
                "order_id": validated_data.get("orderId"),
            },
            status=status.HTTP_200_OK,
        )
