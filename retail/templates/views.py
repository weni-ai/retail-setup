from typing import cast

from rest_framework.viewsets import ViewSet
from rest_framework.views import APIView
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
    TemplateMetricsRequestSerializer,
    UpdateTemplateContentSerializer,
    UpdateTemplateSerializer,
    UpdateLibraryTemplateSerializer,
    CreateCustomTemplateSerializer,
)

from uuid import UUID

from retail.templates.usecases.template_metrics import FetchTemplateMetricsUseCase


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
        request_serializer = CreateCustomTemplateSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        data: CreateCustomTemplateData = cast(
            CreateCustomTemplateData, request_serializer.validated_data
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


class TemplateMetricsView(APIView):
    """
    Endpoint for retrieving aggregated metrics of all template versions
    associated with a given template UUID, within a specified date range.

    Permissions:
        - Only internal services with appropriate permissions can access this endpoint.

    Request body (application/json):
        {
            "template_uuid": "<uuid>",
            "start": "YYYY-MM-DD",
            "end": "YYYY-MM-DD"
        }

    Returns:
        200 OK:
            {
                ...  # JSON with template metrics data
            }
        400 Bad Request:
            {
                "error": "<description of error>"
            }
    """

    permission_classes = [CanCommunicateInternally]

    def post(self, request, *args, **kwargs):
        serializer = TemplateMetricsRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        template_uuid = data["template_uuid"]
        start = data["start"]
        end = data["end"]

        try:
            use_case = FetchTemplateMetricsUseCase()
            metrics = use_case.execute(
                template_uuid=template_uuid, start=start, end=end
            )
            return Response(metrics, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
