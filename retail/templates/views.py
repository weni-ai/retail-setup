from typing import cast

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.templates.usecases import (
    CreateTemplateUseCase,
    ReadTemplateUseCase,
    CreateTemplateData,
    UpdateTemplateUseCase,
    UpdateTemplateData,
)
from retail.templates.serializers import (
    CreateLibraryTemplateSerializer,
    CreateTemplateSerializer,
    ReadTemplateSerializer,
    UpdateTemplateSerializer,
)

from uuid import UUID

from retail.templates.usecases.create_library_template import (
    CreateLibraryTemplateData,
    CreateLibraryTemplateUseCase,
)


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

    @action(detail=False, methods=["patch"])
    def status(self, request: Request) -> Response:
        request_serializer = UpdateTemplateSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: UpdateTemplateData = request_serializer.data
        use_case = UpdateTemplateUseCase()
        template = use_case.execute(data)

        response_serializer = ReadTemplateSerializer(template)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    @action(detail=False, methods=["POST"], url_path="create-library-template")
    def create_library_template(self, request: Request) -> Response:
        request_serializer = CreateLibraryTemplateSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: CreateLibraryTemplateData = cast(
            CreateLibraryTemplateData, request_serializer.validated_data
        )

        use_case = CreateLibraryTemplateUseCase()
        template = use_case.execute(data)

        response_serializer = ReadTemplateSerializer(template)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)
