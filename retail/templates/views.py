import logging

from typing import cast

from uuid import UUID

from rest_framework.viewsets import ViewSet
from rest_framework.views import APIView
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from retail.internal.permissions import CanCommunicateInternally, HasProjectPermission
from retail.templates.exceptions import (
    MetaInvalidResponseError,
    MetaSampleUnavailableError,
    NotDirectSendEligibleError,
    WabaNotConfiguredError,
)
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
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleDTO,
    ValidateTemplateSampleUseCase,
)

from retail.templates.serializers import (
    CreateTemplateSerializer,
    ReadTemplateSerializer,
    TemplateMetricsRequestSerializer,
    UpdateTemplateContentSerializer,
    UpdateTemplateSerializer,
    UpdateLibraryTemplateSerializer,
    CreateCustomTemplateSerializer,
    ValidateTemplateSampleSerializer,
)

from retail.templates.usecases.template_metrics import FetchTemplateMetricsUseCase


logger = logging.getLogger(__name__)


_SAMPLE_DOMAIN_ERROR_HTTP_TRANSLATIONS = {
    NotDirectSendEligibleError: (
        status.HTTP_400_BAD_REQUEST,
        "Template is not Direct Send-eligible",
        "not_direct_send_eligible",
    ),
    WabaNotConfiguredError: (
        status.HTTP_400_BAD_REQUEST,
        "WABA not configured for this project",
        "waba_not_configured",
    ),
    MetaSampleUnavailableError: (
        status.HTTP_502_BAD_GATEWAY,
        "Meta sample submission failed",
        "meta_unavailable",
    ),
    MetaInvalidResponseError: (
        status.HTTP_502_BAD_GATEWAY,
        "Meta did not return a category",
        "meta_invalid_response",
    ),
}


class TemplateViewSet(ViewSet):
    permission_classes = [IsAuthenticated, HasProjectPermission]

    def get_permissions(self):
        permissions = super().get_permissions()

        if self.action == "status":
            return [CanCommunicateInternally()]

        return permissions

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

    @action(detail=True, methods=["post"])
    def sample(self, request: Request, pk: UUID) -> Response:
        """``POST /api/v3/templates/<uuid>/sample/`` — pre-validate against Meta.

        Thin DRF action wiring (Constitution Principle I): validate input
        via ``ValidateTemplateSampleSerializer``, build the frozen DTO,
        delegate to the use case, and translate any domain exception via
        ``_sample_domain_error_to_response`` per FR-007 / FR-007b–e.

        The serializer is instantiated with ``context={"request": request}``
        so its FR-002b ``validate_project_uuid`` method can read the
        ``Project-Uuid`` header for the cross-tenant isolation check
        (SC-008). A mismatch surfaces as HTTP 400 with
        ``error_code = "project_uuid_mismatch"`` and the audit-log
        WARNING line emitted by ``_warn_project_uuid_mismatch``.
        """
        request_serializer = ValidateTemplateSampleSerializer(
            data=request.data, context={"request": request}
        )
        try:
            request_serializer.is_valid(raise_exception=True)
        except ValidationError as exc:
            self._warn_project_uuid_mismatch_if_present(request, pk, exc)
            raise

        dto = self._build_validate_sample_dto(
            request_serializer.validated_data, str(pk)
        )
        use_case = ValidateTemplateSampleUseCase()
        try:
            result = use_case.execute(dto)
        except tuple(_SAMPLE_DOMAIN_ERROR_HTTP_TRANSLATIONS) as exc:
            return self._sample_domain_error_to_response(exc)

        return Response(result.to_dict(), status=status.HTTP_200_OK)

    @staticmethod
    def _sample_domain_error_to_response(exc: Exception) -> Response:
        """Translate a sample-validation domain exception into its HTTP response.

        ``_SAMPLE_DOMAIN_ERROR_HTTP_TRANSLATIONS`` is the single source of
        truth for the four ``(status, detail, error_code)`` triples pinned
        by ``contracts/sample-endpoint-request-response.md`` (FR-007 /
        FR-007b–e). The ``meta_response`` field is forwarded verbatim when
        the exception carries one — ``MetaInvalidResponseError`` always
        sets it, ``MetaSampleUnavailableError`` sets it only when the
        upstream provided a parseable error envelope (FR-007b).
        """
        http_status, detail, error_code = _SAMPLE_DOMAIN_ERROR_HTTP_TRANSLATIONS[
            type(exc)
        ]
        body = {"detail": detail, "error_code": error_code}
        meta_response = getattr(exc, "meta_response", None)
        if meta_response is not None:
            body["meta_response"] = meta_response
        return Response(body, status=http_status)

    def _build_validate_sample_dto(
        self, validated_data: dict, template_uuid: str
    ) -> ValidateTemplateSampleDTO:
        return ValidateTemplateSampleDTO(
            template_uuid=template_uuid,
            template_body=validated_data.get("template_body"),
            template_header=validated_data.get("template_header"),
            template_footer=validated_data.get("template_footer"),
            template_button=validated_data.get("template_button"),
            template_body_params=validated_data.get("template_body_params"),
            app_uuid=validated_data["app_uuid"],
            project_uuid=validated_data["project_uuid"],
            parameters=validated_data.get("parameters"),
            language=validated_data.get("language"),
        )

    def _warn_project_uuid_mismatch_if_present(
        self, request: Request, template_uuid: UUID, exc: ValidationError
    ) -> None:
        """Emit the FR-008a ``project_uuid_mismatch`` audit-log line on mismatch.

        Inspects the DRF ``ValidationError`` for the serializer-layer
        ``project_uuid_mismatch`` code and, when present, emits a WARNING
        line with the BOTH project UUIDs so dashboards can drill down on
        cross-tenant misuse attempts (SC-008). The DRF default 400
        response is re-raised by the caller in any case — this method
        only handles the audit-log side effect.
        """
        if not self._validation_error_has_project_uuid_mismatch(exc):
            return

        logger.warning(
            "[TemplateSampleValidation] project_uuid_mismatch: "
            f"header_project_uuid={request.headers.get('Project-Uuid')} "
            f"body_project_uuid={request.data.get('project_uuid')} "
            f"template_uuid={template_uuid}"
        )

    @staticmethod
    def _validation_error_has_project_uuid_mismatch(exc: ValidationError) -> bool:
        detail = exc.detail
        if not isinstance(detail, dict):
            return False
        project_uuid_errors = detail.get("project_uuid") or []
        return any(
            getattr(err, "code", None) == "project_uuid_mismatch"
            for err in project_uuid_errors
        )


class TemplateLibraryViewSet(ViewSet):
    permission_classes = [IsAuthenticated, HasProjectPermission]

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
            "language": request_serializer.validated_data.get("language"),
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
