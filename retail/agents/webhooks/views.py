from uuid import UUID

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from retail.vtex.tasks import task_order_status_agent_webhook


class AgentWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request, webhook_uuid: UUID, *args, **kwargs) -> Response:
        # Ignoring specific UUID: d30bcce8-ce67-4677-8a33-c12b62a51d4f
        if str(webhook_uuid) != "d30bcce8-ce67-4677-8a33-c12b62a51d4f":
            task_order_status_agent_webhook.apply_async(
                args=[webhook_uuid, request.data, request.query_params],
                queue="vtex-io-orders-update-events",
            )

        return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)
