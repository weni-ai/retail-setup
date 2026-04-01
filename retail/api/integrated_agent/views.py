from uuid import UUID

from rest_framework import status
from rest_framework.response import Response
from rest_framework.request import Request

from retail.api.base_service_view import BaseServiceView
from retail.api.integrated_agent.serializers import SendTestTemplateSerializer
from retail.api.integrated_agent.usecases.dto import SendTestTemplateDTO
from retail.api.integrated_agent.usecases.send_test_template import (
    SendTestTemplateUseCase,
)
from retail.internal.authenticators import InternalOIDCAuthentication


class SendTestTemplateView(BaseServiceView):
    authentication_classes = [InternalOIDCAuthentication]

    def post(self, request: Request, integrated_agent_uuid: UUID) -> Response:
        serializer = SendTestTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dto = SendTestTemplateDTO(
            integrated_agent_uuid=integrated_agent_uuid,
            **serializer.validated_data,
        )

        use_case = SendTestTemplateUseCase(flows_service=self.flows_service)
        use_case.execute(dto)

        return Response(status=status.HTTP_204_NO_CONTENT)
