from typing import cast

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.exceptions import ValidationError
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.templates.usecases import (
    CreateTemplateUseCase,
    ReadTemplateUseCase,
    CreateTemplateData,
    UpdateTemplateUseCase,
    UpdateTemplateData,
    UpdateTemplateContentData,
    UpdateTemplateContentUseCase,
    UpdateLibraryTemplateUseCase,
    UpdateLibraryTemplateData,
    DeleteTemplateUseCase,
    CreateCustomTemplateUseCase,
    CreateCustomTemplateData,
)

from retail.templates.serializers import (
    CreateTemplateSerializer,
    ReadTemplateSerializer,
    UpdateTemplateContentSerializer,
    UpdateTemplateSerializer,
    UpdateLibraryTemplateSerializer,
    CreateCustomTemplateSerializer,
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

    @action(detail=False, methods=["patch"])
    def status(self, request: Request) -> Response:
        request_serializer = UpdateTemplateSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: UpdateTemplateData = request_serializer.data
        use_case = UpdateTemplateUseCase()
        template = use_case.execute(data)

        response_serializer = ReadTemplateSerializer(template)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request: Request, pk: UUID) -> Response:
        """
        Partially updates a template instance by modifying its message body.

        This endpoint is intended to allow editing only the 'body' field of an
        existing template, using its metadata as base. A new version is created
        and propagated to the integrations layer.

        Expected payload:
            {
                "template_body": "<new body string with {{placeholders}}>",
                "app_uuid": "<application identifier>",
                "project_uuid": "<project identifier>"
            }

        URL format:
            PATCH /templates/{uuid}/

        Returns:
            200 OK with updated template data.
        """
        request_serializer = UpdateTemplateContentSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: UpdateTemplateContentData = cast(
            UpdateTemplateContentData,
            {
                **request_serializer.validated_data,
                "template_uuid": str(pk),
            },
        )

        use_case = UpdateTemplateContentUseCase()
        updated_template = use_case.execute(data)

        response_serializer = ReadTemplateSerializer(updated_template)
        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def destroy(self, request: Request, pk: UUID) -> Response:
        use_case = DeleteTemplateUseCase()
        use_case.execute(pk)

        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=["post"])
    def custom(self, request: Request, *args, **kwargs) -> Response:
        integrated_agent_uuid = request.query_params.pop("integrated_agent_uuid")

        if integrated_agent_uuid is None:
            raise ValidationError(
                detail={"missing_fields": "integrate_agent_uuid param missing."}
            )

        request_serializer = CreateCustomTemplateSerializer(request.data)
        request_serializer.is_valid(raise_exception=True)

        data: CreateCustomTemplateData = cast(
            CreateCustomTemplateData,
            {
                **request_serializer.data,
                "integrated_agent_uuid": integrated_agent_uuid,
            },
        )
        use_case = CreateCustomTemplateUseCase()
        template = use_case.execute(data)

        response_serializer = ReadTemplateSerializer(template)
        return Response(data=response_serializer.data, status=status.HTTP_201_CREATED)


class TemplateLibraryViewSet(ViewSet):
    permission_classes = [CanCommunicateInternally]

    def partial_update(self, request: Request, pk: UUID) -> Response:
        request_serializer = UpdateLibraryTemplateSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        app_uuid = request.query_params.get("app_uuid")
        project_uuid = request.query_params.get("project_uuid")

        if not app_uuid or not project_uuid:
            return Response(
                {"error": "app_uuid and project_uuid are required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data: UpdateLibraryTemplateData = {
            "template_uuid": str(pk),
            "app_uuid": app_uuid,
            "project_uuid": project_uuid,
            "library_template_button_inputs": request_serializer.validated_data.get(
                "library_template_button_inputs"
            ),
        }

        use_case = UpdateLibraryTemplateUseCase()
        template = use_case.execute(data)

        response_serializer = ReadTemplateSerializer(template)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
