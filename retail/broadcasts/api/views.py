"""HTTP layer for broadcast dispatch and conversion report APIs."""

from typing import Optional
from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound, ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.permissions import IsIntegratedAgentFromProject
from retail.broadcasts.api.serializers import (
    BroadcastDispatchRowSerializer,
    BroadcastSummarySerializer,
    GetBroadcastSummaryQuerySerializer,
    GetPaymentRecoveryConversionMetricsQuerySerializer,
    ListBroadcastDispatchesQuerySerializer,
    PaymentRecoveryConversionMetricsSerializer,
)
from retail.broadcasts.usecases.get_broadcast_summary import (
    GetBroadcastSummaryDTO,
    GetBroadcastSummaryUseCase,
)
from retail.broadcasts.usecases.get_payment_recovery_conversion_metrics import (
    GetPaymentRecoveryConversionMetricsDTO,
    GetPaymentRecoveryConversionMetricsUseCase,
)
from retail.broadcasts.usecases.list_broadcast_dispatches import (
    ListBroadcastDispatchesDTO,
    ListBroadcastDispatchesUseCase,
)
from retail.internal.permissions import HasProjectPermission
from retail.internal.views import KeycloakAPIView


class _BroadcastReportBaseView(KeycloakAPIView):
    permission_classes = [IsAuthenticated, HasProjectPermission]

    @staticmethod
    def _parse_project_uuid(request: Request) -> UUID:
        try:
            return UUID(request.headers.get("Project-Uuid"))
        except (TypeError, ValueError) as exc:
            raise ParseError("Project-Uuid header must be a valid UUID.") from exc

    @staticmethod
    def _build_dispatches_response(
        dto: ListBroadcastDispatchesDTO,
        rows: list,
        total: int,
    ) -> Response:
        row_serializer = BroadcastDispatchRowSerializer(rows, many=True)
        return Response(
            {
                "results": row_serializer.data,
                "pagination": {
                    "page": dto.page,
                    "page_size": dto.page_size,
                    "total": total,
                },
            },
            status=status.HTTP_200_OK,
        )

    def _list_dispatches(
        self,
        request: Request,
        *,
        project_uuid: UUID,
        integrated_agent_uuid: Optional[UUID] = None,
    ) -> Response:
        query_serializer = ListBroadcastDispatchesQuerySerializer(
            data=request.query_params
        )
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data

        dto = ListBroadcastDispatchesDTO(
            project_uuid=project_uuid,
            integrated_agent_uuid=integrated_agent_uuid,
            start_date=validated["start_date"],
            end_date=validated["end_date"],
            page=validated.get("page", 1),
            page_size=validated.get("page_size", 20),
        )
        rows, total = ListBroadcastDispatchesUseCase().execute(dto)
        return self._build_dispatches_response(dto, rows, total)

    def _build_summary_response(
        self,
        request: Request,
        *,
        project_uuid: UUID,
        integrated_agent_uuid: Optional[UUID] = None,
    ) -> Response:
        query_serializer = GetBroadcastSummaryQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data

        dto = GetBroadcastSummaryDTO(
            project_uuid=project_uuid,
            integrated_agent_uuid=integrated_agent_uuid,
            start_date=validated["start_date"],
            end_date=validated["end_date"],
        )
        result = GetBroadcastSummaryUseCase().execute(dto)
        return Response(
            BroadcastSummarySerializer(result).data,
            status=status.HTTP_200_OK,
        )

    def _build_payment_recovery_conversion_response(
        self,
        request: Request,
        *,
        project_uuid: UUID,
        integrated_agent_uuid: Optional[UUID] = None,
    ) -> Response:
        query_serializer = GetPaymentRecoveryConversionMetricsQuerySerializer(
            data=request.query_params
        )
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data

        dto = GetPaymentRecoveryConversionMetricsDTO(
            project_uuid=project_uuid,
            integrated_agent_uuid=integrated_agent_uuid,
            start_date=validated["start_date"],
            end_date=validated["end_date"],
        )
        result = GetPaymentRecoveryConversionMetricsUseCase().execute(dto)
        return Response(
            PaymentRecoveryConversionMetricsSerializer(result).data,
            status=status.HTTP_200_OK,
        )


class BroadcastProjectDispatchesView(_BroadcastReportBaseView):
    """GET ``/api/v3/broadcasts/projects/dispatches/`` — project-wide report."""

    def get(self, request: Request) -> Response:
        return self._list_dispatches(
            request,
            project_uuid=self._parse_project_uuid(request),
        )


class _BroadcastAgentReportBaseView(_BroadcastReportBaseView):
    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsIntegratedAgentFromProject,
    ]

    def _get_integrated_agent(
        self, request: Request, agent_uuid: UUID
    ) -> IntegratedAgent:
        try:
            integrated_agent = IntegratedAgent.objects.select_related("project").get(
                uuid=agent_uuid
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {agent_uuid}")

        self.check_object_permissions(request, integrated_agent)
        return integrated_agent


class BroadcastAgentDispatchesView(_BroadcastAgentReportBaseView):
    """GET ``/api/v3/broadcasts/assigneds/{agent_uuid}/dispatches/``."""

    def get(self, request: Request, agent_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)
        return self._list_dispatches(
            request,
            project_uuid=integrated_agent.project.uuid,
            integrated_agent_uuid=integrated_agent.uuid,
        )


class BroadcastProjectSummaryView(_BroadcastReportBaseView):
    """GET ``/api/v3/broadcasts/projects/summary/`` — project-wide totals."""

    def get(self, request: Request) -> Response:
        return self._build_summary_response(
            request,
            project_uuid=self._parse_project_uuid(request),
        )


class BroadcastAgentSummaryView(_BroadcastAgentReportBaseView):
    """GET ``/api/v3/broadcasts/assigneds/{agent_uuid}/summary/``."""

    def get(self, request: Request, agent_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)
        return self._build_summary_response(
            request,
            project_uuid=integrated_agent.project.uuid,
            integrated_agent_uuid=integrated_agent.uuid,
        )


class BroadcastProjectPaymentRecoveryConversionView(_BroadcastReportBaseView):
    """GET ``/api/v3/broadcasts/projects/payment-recovery/conversion/``."""

    def get(self, request: Request) -> Response:
        return self._build_payment_recovery_conversion_response(
            request,
            project_uuid=self._parse_project_uuid(request),
        )


class BroadcastAgentPaymentRecoveryConversionView(_BroadcastAgentReportBaseView):
    """GET ``/api/v3/broadcasts/assigneds/{agent_uuid}/payment-recovery/conversion/``."""

    def get(self, request: Request, agent_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)
        return self._build_payment_recovery_conversion_response(
            request,
            project_uuid=integrated_agent.project.uuid,
            integrated_agent_uuid=integrated_agent.uuid,
        )
