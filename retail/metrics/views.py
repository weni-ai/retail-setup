from rest_framework import status
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from retail.internal.weni_mixins import WeniAuthMixin
from retail.metrics.exceptions import ProductMetricPublishError, ProjectNotFoundError
from retail.metrics.serializers import RecordProductMetricEventSerializer
from retail.metrics.usecases.record_product_metric_event import (
    RecordProductMetricEventDTO,
    RecordProductMetricEventUseCase,
)


class RecordProductMetricEventView(WeniAuthMixin, APIView):
    """Records a product click for the authenticated user.

    The client sends ``event_type`` and an optional ``suggested_plan``.
    Email and VTEX account come from ``self.auth`` and cannot be set by
    the body. Success is ``204``. A datalake failure is ``502``.
    """

    def post(self, request: Request) -> Response:
        serializer = RecordProductMetricEventSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        validated = serializer.validated_data

        user_email = self.auth.user_email
        if not user_email:
            raise PermissionDenied("user_email could not be resolved from the request.")

        dto = RecordProductMetricEventDTO(
            event_type=validated["event_type"],
            suggested_plan=validated.get("suggested_plan"),
            user_email=user_email,
            vtex_account=self.auth.vtex_account,
            project_uuid=(
                self.auth.project_uuid if self.auth.has_project_uuid else None
            ),
        )

        try:
            RecordProductMetricEventUseCase().execute(dto)
        except ProjectNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except ProductMetricPublishError:
            return Response(status=status.HTTP_502_BAD_GATEWAY)

        return Response(status=status.HTTP_204_NO_CONTENT)
