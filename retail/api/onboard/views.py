import logging

from rest_framework import status
from rest_framework.response import Response

from retail.api.onboard.serializers import (
    ActivateWebchatSerializer,
    ActivateWppCloudSerializer,
)
from retail.api.onboard.usecases.activate_wpp_cloud import ActivateWppCloudUseCase
from retail.api.onboard.usecases.dto import ActivateWebchatDTO, ActivateWppCloudDTO
from retail.api.onboard.usecases.publish_webchat_script import (
    PublishWebchatScriptUseCase,
)
from retail.internal.views import KeycloakAPIView
from retail.services.integrations.service import IntegrationsService
from retail.services.webchat_push.service import WebchatPushService

logger = logging.getLogger(__name__)


class ActivateWebchatView(KeycloakAPIView):
    """
    Publishes the webchat loader script to the customer's S3 bucket.

    Called by the front-end when the user decides to activate
    the webchat widget on their store.
    """

    def post(self, request):
        serializer = ActivateWebchatSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dto = ActivateWebchatDTO(
            app_uuid=str(serializer.validated_data["app_uuid"]),
            account_id=serializer.validated_data["account_id"],
        )

        use_case = PublishWebchatScriptUseCase(
            integrations_service=IntegrationsService(),
            webchat_push_service=WebchatPushService(),
        )

        result = use_case.execute(dto)

        return Response(result.to_dict(), status=status.HTTP_201_CREATED)


class ActivateWppCloudView(KeycloakAPIView):
    """
    Activates the WPP Cloud abandoned cart agent by setting
    its contact_percentage.

    Called by the front-end when the store owner decides to
    activate the abandoned cart notifications.
    """

    def post(self, request):
        serializer = ActivateWppCloudSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dto = ActivateWppCloudDTO(
            project_uuid=str(serializer.validated_data["project_uuid"]),
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
