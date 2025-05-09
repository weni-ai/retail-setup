from rest_framework.viewsets import ViewSet
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.templates.usecases import (
    CreateTemplateUseCase,
    ReadTemplateUseCase,
    CreateTemplateData,
)
from retail.templates.serializers import (
    CreateTemplateSerializer,
    ReadTemplateSerializer,
)

from uuid import UUID


class TemplateViewSet(ViewSet):
    permission_classes = [CanCommunicateInternally]

    def create(self, request: Request) -> Response:
        request_serializer = CreateTemplateSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: CreateTemplateData = request_serializer.data
        use_case = CreateTemplateUseCase()
        template = use_case.execute(data)

        response_serializer = ReadTemplateSerializer(template)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)

    def retrieve(self, request: Request, pk: UUID) -> Response:
        use_case = ReadTemplateUseCase()
        template = use_case.execute(pk)

        response_serializer = ReadTemplateSerializer(template)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
