import json

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from retail.agents.shared.permissions import IsAgentOficialOrFromProjet
from retail.agents.domains.agent_management.serializers import (
    PushAgentSerializer,
    ReadAgentSerializer,
)
from retail.agents.domains.agent_management.tasks import validate_pre_approved_templates
from retail.agents.domains.agent_management.usecases.push import (
    PushAgentUseCase,
    PushAgentData,
)
from retail.agents.domains.agent_management.usecases.list import ListAgentsUseCase
from retail.agents.domains.agent_management.usecases.retrieve import (
    RetrieveAgentUseCase,
)
from retail.internal.permissions import HasProjectPermission


class PushAgentView(APIView):
    permission_classes = [IsAuthenticated]

    def __parse_credentials(self, agent: dict) -> list[dict]:
        credentials = []

        for key, credential in agent.get("credentials", {}).items():
            credentials.append(
                {
                    "key": key,
                    "value": credential.get("credentials", []),
                    "label": credential.get("label"),
                    "placeholder": credential.get("placeholder"),
                    "is_confidential": credential.get("is_confidential"),
                }
            )

        return credentials

    def post(self, request: Request, *args, **kwargs) -> Response:
        try:
            agents = json.loads(request.data.get("agents"))
        except (json.JSONDecodeError, TypeError):
            raise ValidationError({"agents": "Invalid JSON format"})

        project_uuid = request.data.get("project_uuid")

        for agent in agents.get("agents", {}).values():
            agent["credentials"] = self.__parse_credentials(agent)

        data = {**agents, "project_uuid": project_uuid}

        request_serializer = PushAgentSerializer(data=data)
        request_serializer.is_valid(raise_exception=True)

        serialized_data: PushAgentData = request_serializer.data

        use_case = PushAgentUseCase()
        agents = use_case.execute(payload=serialized_data, files=request.FILES)

        agent_ids = [str(agent.uuid) for agent in agents]
        validate_pre_approved_templates.delay(agent_ids)

        response_serializer = ReadAgentSerializer(agents, many=True)
        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class AgentViewSet(ViewSet):
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        permissions = super().get_permissions()

        if self.action == "retrieve":
            permissions.append(IsAgentOficialOrFromProjet())

        return permissions

    def list(self, request: Request, *args, **kwargs) -> Response:
        project_uuid = request.headers.get("Project-Uuid")

        if project_uuid is None:
            raise ValidationError({"project_uuid": "Missing project uuid in header."})

        agents = ListAgentsUseCase.execute(project_uuid)

        response_serializer = ReadAgentSerializer(agents, many=True)

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request: Request, pk=None, *args, **kwargs) -> Response:
        agent = RetrieveAgentUseCase.execute(pk)

        self.check_object_permissions(request, agent)

        response_serializer = ReadAgentSerializer(agent)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
