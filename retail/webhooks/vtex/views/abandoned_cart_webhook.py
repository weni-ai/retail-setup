import logging

from uuid import UUID

from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from retail.agents.domains.agent_webhook.services.integrated_agent_resolver import (
    IntegratedAgentWebhookResolver,
)
from retail.webhooks.vtex.serializers import ExternalAbandonedCartSerializer
from retail.webhooks.vtex.usecases.dto import ProcessAbandonedCartNotificationDTO
from retail.webhooks.vtex.usecases.process_abandoned_cart_notification import (
    ProcessAbandonedCartNotificationUseCase,
)


logger = logging.getLogger(__name__)


class AbandonedCartWebhookView(APIView):
    """External webhook endpoint for abandoned cart notifications."""

    permission_classes = [AllowAny]

    def post(self, request: Request, pk: UUID) -> Response:
        if request.data.get("hookConfig") == "ping":
            logger.info(f"[AbandonedCart] VTEX ping received - agent={pk}")
            return self._webhook_received_response()

        try:
            integrated_agent = IntegratedAgentWebhookResolver().resolve(pk)
            if integrated_agent is None:
                logger.warning(
                    f"[AbandonedCart] Integrated agent not found or blocked - agent={pk}"
                )
                return self._webhook_received_response()

            serializer = ExternalAbandonedCartSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            dto = ProcessAbandonedCartNotificationDTO(
                order_form_id=serializer.validated_data["cart_id"],
                phone=serializer.validated_data["phone"],
                name=serializer.validated_data["name"],
            )
            ProcessAbandonedCartNotificationUseCase.from_integrated_agent(
                integrated_agent
            ).execute(dto)
        except Exception as exc:
            logger.exception(
                f"[AbandonedCart] Failed to process webhook - agent={pk}: {exc}"
            )

        return self._webhook_received_response()

    @staticmethod
    def _webhook_received_response() -> Response:
        return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)
