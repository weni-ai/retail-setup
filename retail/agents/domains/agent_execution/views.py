"""HTTP layer for the public agent-logs API.

Two endpoints, both scoped to a single ``IntegratedAgent`` via the URL
and to a single project via the ``Project-Uuid`` header:

- ``GET /api/v3/agents/assigneds/{agent_uuid}/logs/`` — paginated list.
- ``POST /api/v3/agents/assigneds/{agent_uuid}/logs/export/`` — async
  CSV export request.

The views stay thin — query/body validation, DTO assembly, and
delegation to the corresponding use case. All the row mapping lives in
``serializers`` + ``row_mapper``, and all the filter logic lives in
the use cases.
"""

import logging
from typing import Optional
from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from retail.agents.domains.agent_execution.serializers import (
    AgentLogRowSerializer,
    ExportAgentLogsBodySerializer,
    ListAgentLogsQuerySerializer,
)
from retail.agents.domains.agent_execution.usecases.list_agent_logs import (
    ListAgentLogsFilter,
    ListAgentLogsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.permissions import IsIntegratedAgentFromProject
from retail.agents.tasks import task_export_agent_logs
from retail.internal.permissions import HasProjectPermission
from retail.internal.views import KeycloakAPIView
from retail.services.aws_s3.service import S3Service


logger = logging.getLogger(__name__)


class _AgentLogsBaseView(KeycloakAPIView):
    """Shared agent-uuid + project-uuid resolution and authorization."""

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

        # Object-level check verifies the agent belongs to the project
        # carried in the ``Project-Uuid`` header.
        self.check_object_permissions(request, integrated_agent)
        return integrated_agent

    @staticmethod
    def _project_uuid(request: Request) -> Optional[str]:
        return request.headers.get("Project-Uuid")


class AgentLogsView(_AgentLogsBaseView):
    """GET ``/assigneds/{agent_uuid}/logs/``."""

    def get(self, request: Request, agent_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)

        query_serializer = ListAgentLogsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data

        dto = ListAgentLogsFilter(
            agent_uuid=integrated_agent.uuid,
            project_uuid=integrated_agent.project.uuid,
            search=validated.get("search") or None,
            date=validated.get("date"),
            template_uuids=tuple(validated.get("template_uuids") or ()),
            statuses=tuple(validated.get("statuses") or ()),
            page=validated.get("page", 1),
            page_size=validated.get("page_size", 20),
        )

        rows, total = ListAgentLogsUseCase().execute(dto)

        s3_service = self._build_s3_service()
        row_serializer = AgentLogRowSerializer(rows, many=True, s3_service=s3_service)

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

    @staticmethod
    def _build_s3_service() -> Optional[S3Service]:
        """Build an S3 service bound to the traces bucket, or ``None`` if unavailable.

        The serializer falls back to ``json_url=null`` when no S3
        client can be built (typical in unit tests without AWS
        credentials), so a missing service never fails the request.
        """
        from django.conf import settings

        bucket_name = getattr(settings, "EXECUTION_TRACES_BUCKET", None) or getattr(
            settings, "AWS_STORAGE_BUCKET_NAME", None
        )
        if not bucket_name:
            return None
        try:
            return S3Service(bucket_name=bucket_name)
        except Exception:
            return None


class AgentLogsExportView(_AgentLogsBaseView):
    """POST ``/assigneds/{agent_uuid}/logs/export/``."""

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)

        body_serializer = ExportAgentLogsBodySerializer(data=request.data)
        body_serializer.is_valid(raise_exception=True)
        validated = body_serializer.validated_data

        date_value = validated.get("date")
        task_export_agent_logs.apply_async(
            kwargs={
                "agent_uuid": str(integrated_agent.uuid),
                "project_uuid": str(integrated_agent.project.uuid),
                "search": validated.get("search") or None,
                "date": date_value.isoformat() if date_value else None,
                "template_uuids": [
                    str(uuid) for uuid in (validated.get("template_uuids") or [])
                ],
                "statuses": list(validated.get("statuses") or []),
            }
        )

        return Response({"requested": True}, status=status.HTTP_202_ACCEPTED)
