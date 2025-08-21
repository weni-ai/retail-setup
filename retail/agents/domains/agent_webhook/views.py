from typing import ClassVar

from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from uuid import UUID

from retail.vtex.tasks import task_order_status_agent_webhook


class AgentWebhookView(APIView):
    IGNORE_AGENT_UUID: ClassVar[str] = "d30bcce8-ce67-4677-8a33-c12b62a51d4f"
    permission_classes = [AllowAny]

    def post(self, request: Request, webhook_uuid: UUID, *args, **kwargs) -> Response:
        if str(webhook_uuid) != self.IGNORE_AGENT_UUID:
            task_order_status_agent_webhook.apply_async(
                args=[webhook_uuid, request.data, request.query_params],
                queue="vtex-io-orders-update-events",
            )

        return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)
