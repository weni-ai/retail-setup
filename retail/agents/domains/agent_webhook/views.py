import logging

from rest_framework.views import APIView
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework import status

from uuid import UUID

from retail.agents.domains.agent_webhook.services.integrated_agent_resolver import (
    IGNORE_INTEGRATED_AGENT_UUID,
    IntegratedAgentWebhookResolver,
)
from retail.vtex.tasks import task_agent_webhook


logger = logging.getLogger(__name__)


class AgentWebhookView(APIView):
    IGNORE_AGENT_UUID = IGNORE_INTEGRATED_AGENT_UUID
    permission_classes = [AllowAny]

    def post(self, request: Request, webhook_uuid: UUID, *args, **kwargs) -> Response:
        if str(webhook_uuid) == IGNORE_INTEGRATED_AGENT_UUID:
            return self._webhook_received_response()

        if request.data.get("hookConfig") == "ping":
            logger.info(
                f"[AgentWebhook] VTEX ping received - integrated_agent={webhook_uuid}"
            )
            return self._webhook_received_response()

        if IntegratedAgentWebhookResolver().should_skip_generic_webhook_dispatch(
            webhook_uuid
        ):
            return self._webhook_received_response()

        payload = dict(request.data)
        payload["Origin"] = {"Sender": "agent-webhook"}

        task_agent_webhook.apply_async(
            args=[str(webhook_uuid), payload, dict(request.query_params)],
            queue="vtex-io-orders-update-events",
        )

        return self._webhook_received_response()

    @staticmethod
    def _webhook_received_response() -> Response:
        return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)
