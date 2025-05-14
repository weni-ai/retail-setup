import json

from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from retail.agents.serializers import PushAgentSerializer, ReadAgentSerializer
from retail.agents.usecases import (
    PushAgentUseCase,
    PushAgentData,
    ListAgentsUseCase,
    RetrieveAgentUseCase,
)
from retail.agents.tasks import validate_pre_approved_templates
from retail.agents.permissions import IsAgentOficialOrFromProjet
from retail.internal.permissions import CanCommunicateInternally


class PushAgentView(APIView):
    permission_classes = [CanCommunicateInternally]

    def post(self, request: Request, *args, **kwargs) -> Response:
        agents = json.loads(request.data.get("agents"))
        project_uuid = request.data.get("project_uuid")

        data = {**agents, "project_uuid": project_uuid}

        request_serializer = PushAgentSerializer(data=data)
        request_serializer.is_valid(raise_exception=True)

        data: PushAgentData = request_serializer.data
        use_case = PushAgentUseCase()
        agents = use_case.execute(payload=data, files=request.FILES)

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
        project_uuid = request.headers.get("Project-Uuid")

        if project_uuid is None:
            raise ValidationError({"project_uuid": "Missing project uuid in header."})

        agent = RetrieveAgentUseCase.execute(pk)

        self.check_object_permissions(request, agent)

        response_serializer = ReadAgentSerializer(agent)
        return Response(response_serializer.data, status=status.HTTP_200_OK)
