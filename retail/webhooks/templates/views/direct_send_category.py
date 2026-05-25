from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from retail.internal.permissions import CanCommunicateInternally
from retail.webhooks.templates.serializers import (
    DirectSendCategoryWebhookSerializer,
)
from retail.webhooks.templates.usecases.direct_send_category import (
    DirectSendCategoryDTO,
    DirectSendCategoryWebhookUseCase,
)


class DirectSendCategoryWebhook(APIView):
    """Inbound webhook called by Integrations when Meta-side
    category-detection determines a Direct Send template's category is
    wrong (FR-001 / FR-002).

    The view is thin: payload validation lives in the serializer, every
    business rule (lookup, fan-out, flagging, audit log) lives in the
    use case, authorization is expressed exclusively via
    ``permission_classes``.
    """

    permission_classes = [CanCommunicateInternally]

    def post(self, request):
        serializer = DirectSendCategoryWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dto = DirectSendCategoryDTO(**serializer.validated_data)
        use_case = DirectSendCategoryWebhookUseCase()

        try:
            result = use_case.execute(dto)
        except Exception:
            return Response(
                {"detail": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(result.to_dict(), status=status.HTTP_200_OK)
