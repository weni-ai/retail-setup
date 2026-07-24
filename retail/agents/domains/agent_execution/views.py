"""HTTP layer for the public agent-logs API.

Three endpoints, all scoped to a single ``IntegratedAgent`` via the URL
and to a single project resolved from the authenticated context
(``self.auth``, populated by the unified JWT + Keycloak flow):

- ``GET /api/v3/agents/assigneds/{agent_uuid}/logs/`` — paginated list.
- ``GET /api/v3/agents/assigneds/{agent_uuid}/logs/{log_uuid}/json/`` —
  server-side proxy that reads the stored trace payload from S3.
- ``POST /api/v3/agents/assigneds/{agent_uuid}/logs/export/`` — async
  CSV export request.

The views stay thin — query/body validation, DTO assembly, and
delegation to the corresponding use case. All row mapping lives in
``serializers`` + ``row_mapper``, all filter logic and S3 reads live in
the use cases (so the views never touch S3).
"""

import logging
from uuid import UUID

from django.http import HttpResponseRedirect
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from weni_commons.auth import IsWeniAuthenticated

from retail.agents.domains.agent_execution.serializers import (
    AgentLogRowSerializer,
    ExportAgentLogsBodySerializer,
    ExportDownloadQuerySerializer,
    ListAgentLogsQuerySerializer,
)
from retail.agents.domains.agent_execution.usecases.export_download import (
    ResolveExportDownloadUseCase,
)
from retail.agents.domains.agent_execution.usecases.get_agent_log_json import (
    GetAgentLogJsonDTO,
    GetAgentLogJsonUseCase,
)
from retail.agents.domains.agent_execution.usecases.list_agent_logs import (
    ListAgentLogsDTO,
    ListAgentLogsUseCase,
)
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.permissions import IsIntegratedAgentFromProject
from retail.agents.tasks import task_export_agent_logs
from retail.internal.permissions import HasWeniProjectPermission
from retail.internal.weni_mixins import WeniAuthMixin


logger = logging.getLogger(__name__)


class _AgentLogsBaseView(WeniAuthMixin, APIView):
    """Shared agent-uuid + project-uuid resolution and authorization."""

    permission_classes = [
        IsWeniAuthenticated,
        HasWeniProjectPermission,
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
        # resolved from the authenticated context.
        self.check_object_permissions(request, integrated_agent)
        return integrated_agent


class AgentLogsView(_AgentLogsBaseView):
    """GET ``/assigneds/{agent_uuid}/logs/``."""

    def get(self, request: Request, agent_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)

        query_serializer = ListAgentLogsQuerySerializer(data=request.query_params)
        query_serializer.is_valid(raise_exception=True)
        validated = query_serializer.validated_data

        dto = ListAgentLogsDTO(
            agent_uuid=integrated_agent.uuid,
            project_uuid=integrated_agent.project.uuid,
            search=validated.get("search") or None,
            start_date=validated.get("start_date"),
            end_date=validated.get("end_date"),
            template_uuids=tuple(validated.get("template_uuids") or ()),
            statuses=tuple(validated.get("statuses") or ()),
            page=validated.get("page", 1),
            page_size=validated.get("page_size", 20),
        )

        rows, total = ListAgentLogsUseCase().execute(dto)
        row_serializer = AgentLogRowSerializer(rows, many=True)

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


class AgentLogJsonView(_AgentLogsBaseView):
    """GET ``/assigneds/{agent_uuid}/logs/{log_uuid}/json/``.

    Proxies the stored trace payload from S3 server-side so the browser
    never fetches it cross-origin.
    """

    def get(self, request: Request, agent_uuid: UUID, log_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)

        dto = GetAgentLogJsonDTO(
            agent_uuid=integrated_agent.uuid,
            project_uuid=integrated_agent.project.uuid,
            log_uuid=log_uuid,
        )
        payload = GetAgentLogJsonUseCase().execute(dto)

        return Response(payload, status=status.HTTP_200_OK)


class AgentLogsExportView(_AgentLogsBaseView):
    """POST ``/assigneds/{agent_uuid}/logs/export/``."""

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        integrated_agent = self._get_integrated_agent(request, agent_uuid)

        body_serializer = ExportAgentLogsBodySerializer(data=request.data)
        body_serializer.is_valid(raise_exception=True)
        validated = body_serializer.validated_data

        start_date = validated.get("start_date")
        end_date = validated.get("end_date")
        task_export_agent_logs.apply_async(
            kwargs={
                "agent_uuid": str(integrated_agent.uuid),
                "project_uuid": str(integrated_agent.project.uuid),
                "user_email": validated.get("user_email"),
                "search": validated.get("search") or None,
                "start_date": start_date.isoformat() if start_date else None,
                "end_date": end_date.isoformat() if end_date else None,
                "template_uuids": [
                    str(uuid) for uuid in (validated.get("template_uuids") or [])
                ],
                "statuses": list(validated.get("statuses") or []),
            }
        )

        return Response({"requested": True}, status=status.HTTP_202_ACCEPTED)


class AgentLogsExportDownloadView(APIView):
    """GET ``/logs/export/download/?token=...``.

    Public, token-authorized entry point for the link emailed after an
    export. The signed token (not a platform session) authorizes the
    request, mirroring the webhook endpoints, so it works straight from
    the recipient's email client. It mints a fresh, short-lived
    presigned URL and redirects, keeping long-lived presigned URLs out
    of the email entirely.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> HttpResponseRedirect:
        serializer = ExportDownloadQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)

        url = ResolveExportDownloadUseCase().execute(serializer.validated_data["token"])
        return HttpResponseRedirect(url)
