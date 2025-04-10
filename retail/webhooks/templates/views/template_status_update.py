import logging

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.webhooks.templates.serializers import TemplateStatusSerializer
from retail.webhooks.templates.usecases.template_status_update import TemplateStatusUpdateUseCase


logger = logging.getLogger(__name__)


class TemplatesStatusWebhook(APIView):
    """
    Receives the final status of library templates via webhook
    and updates the integrated_feature accordingly.
    """

    permission_classes = [CanCommunicateInternally]

    def post(self, request, *args, **kwargs):
        serializer = TemplateStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        app_uuid = serializer.validated_data["app_uuid"]
        template_statuses = serializer.validated_data["template_statuses"]

        use_case = TemplateStatusUpdateUseCase()

        try:
            result = use_case.handle(str(app_uuid), template_statuses)
            return Response(
                {
                    "detail": result["final_details"],
                    "integrated_features_updated": result["integrated_features_updated"]
                },
                status=status.HTTP_200_OK
            )
        except ValueError as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(f"Unexpected error in TemplatesStatusWebhook: {str(e)}")
            return Response(
                {"detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
