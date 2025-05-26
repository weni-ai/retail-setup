from typing import cast

from rest_framework.viewsets import ViewSet
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework.exceptions import NotFound
from rest_framework import status

from retail.internal.permissions import CanCommunicateInternally
from retail.templates.models import Template
from retail.templates.usecases import (
    CreateTemplateUseCase,
    ReadTemplateUseCase,
    CreateTemplateData,
    UpdateTemplateUseCase,
    UpdateTemplateData,
    UpdateTemplateContentData,
    UpdateTemplateContentUseCase,
    CreateLibraryTemplateUseCase,
    CreateLibraryTemplateData,
)

from retail.templates.serializers import (
    CreateTemplateSerializer,
    ReadTemplateSerializer,
    UpdateTemplateContentSerializer,
    UpdateTemplateSerializer,
    UpdateLibraryTemplateSerializer,
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


class TemplateLibraryViewSet(ViewSet):
    permission_classes = [CanCommunicateInternally]

    def _get_template(self, pk: UUID) -> Template:
        try:
            return Template.objects.get(uuid=pk)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {pk}")

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

        template = self._get_template(pk)

        payload: CreateLibraryTemplateData = {
            "template_name": template.metadata.get("name"),
            "library_template_name": template.metadata.get("name"),
            "category": template.metadata.get("category"),
            "language": template.metadata.get("language"),
            "app_uuid": app_uuid,
            "project_uuid": project_uuid,
            "start_condition": template.parent.start_condition,
            "library_template_button_inputs": request_serializer.validated_data.get(
                "library_template_button_inputs"
            ),
        }

        use_case = CreateLibraryTemplateUseCase()
        use_case.notify_integrations(
            template.current_version.template_name,
            template.current_version.uuid,
            payload,
        )

        return Response(
            data={"message": "Created library template task triggered."},
            status=status.HTTP_200_OK,
        )
