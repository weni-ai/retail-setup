import logging

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from weni_commons.auth import IsWeniAuthenticated

from retail.api.onboard.serializers import (
    ActivateWebchatSerializer,
    ActivateWppCloudSerializer,
)
from retail.api.onboard.usecases.activate_wpp_cloud import ActivateWppCloudUseCase
from retail.api.onboard.usecases.dto import ActivateWebchatDTO, ActivateWppCloudDTO
from retail.api.onboard.usecases.publish_webchat_script import (
    PublishWebchatScriptUseCase,
)
from retail.internal.permissions import HasWeniProjectPermission
from retail.internal.weni_mixins import WeniAuthMixin
from retail.services.integrations.service import IntegrationsService
from retail.services.webchat_push.service import WebchatPushService

logger = logging.getLogger(__name__)


class ActivateWebchatView(WeniAuthMixin, APIView):
    """
    Publishes the webchat loader script to the customer's S3 bucket.

    Called by the front-end when the user decides to activate
    the webchat widget on their store.
    """

    permission_classes = [IsWeniAuthenticated, HasWeniProjectPermission]

    def post(self, request):
        serializer = ActivateWebchatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dto = ActivateWebchatDTO(
            app_uuid=str(serializer.validated_data["app_uuid"]),
            account_id=self._resolve_account_id(request),
            vtex_account=self.auth.vtex_account,
        )

        use_case = PublishWebchatScriptUseCase(
            integrations_service=IntegrationsService(),
            webchat_push_service=WebchatPushService(),
        )

        result = use_case.execute(dto)

        return Response(result.to_dict(), status=status.HTTP_201_CREATED)

    def _resolve_account_id(self, request: Request) -> str:
        """Resolve the account identity, preferring the JWT claim.

        TODO(rollout): drop the request-body fallback once every IO
        deployment sends ``account_id`` in the JWT. Older IO versions still
        send it in the body, so during the transition the token is trusted
        first and the body value is accepted only when the claim is absent.

        Args:
            request: The incoming DRF request.

        Returns:
            The resolved account identity.

        Raises:
            ValidationError: When the claim is absent from both the token and
                the request body.
        """
        if self.auth.has_account_id:
            return self.auth.account_id

        account_id = request.data.get("account_id")
        if not account_id:
            raise ValidationError(
                {"account_id": "account_id is required for this request."}
            )
        return account_id


class ActivateWppCloudView(WeniAuthMixin, APIView):
    """
    Activates the WPP Cloud abandoned cart agent by setting
    its contact_percentage.

    Called by the front-end when the store owner decides to
    activate the abandoned cart notifications.
    """

    def post(self, request):
        serializer = ActivateWppCloudSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        project_uuid = self.auth.project_uuid

        dto = ActivateWppCloudDTO(
            project_uuid=project_uuid,
            percentage=serializer.validated_data["percentage"],
        )

        use_case = ActivateWppCloudUseCase()
        integrated_agent = use_case.execute(dto)

        return Response(
            {
                "integrated_agent_uuid": str(integrated_agent.uuid),
                "contact_percentage": integrated_agent.contact_percentage,
            },
            status=status.HTTP_200_OK,
        )
