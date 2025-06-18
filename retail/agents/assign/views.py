from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from retail.agents.push.models import Agent
from retail.agents.push.permissions import IsAgentOficialOrFromProjet
from retail.agents.assign.permissions import IsIntegratedAgentFromProject
from retail.agents.assign.serializers import (
    ReadIntegratedAgentSerializer,
    UpdateIntegratedAgentSerializer,
)
from retail.agents.assign.usecases import (
    AssignAgentUseCase,
    UnassignAgentUseCase,
    RetrieveIntegratedAgentUseCase,
    ListIntegratedAgentUseCase,
    UpdateIntegratedAgentUseCase,
    UpdateIntegratedAgentData,
)


def get_project_uuid_from_request(request: Request) -> str:
    project_uuid = request.headers.get("Project-Uuid")
    if project_uuid is None:
        raise ValidationError({"project_uuid": "Missing project uuid in header."})

    return project_uuid


class GenericIntegratedAgentView(APIView):
    def get_agent(self, agent_uuid: UUID) -> Agent:
        try:
            return Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            raise NotFound(f"Agent not found: {agent_uuid}")


class AssignAgentView(GenericIntegratedAgentView):
    permission_classes = [IsAuthenticated, IsAgentOficialOrFromProjet]

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        """
        Receives a agent and a list of credentials and create a IntegratedAgent.

        credentials format:
        [
            {
                "key": "KEY_EXAMPLE",
                "value": "Value Example"
            }
        ]
        """

        project_uuid = get_project_uuid_from_request(request)
        credentials = request.data.get("credentials", {})
        include_templates = request.data.get("templates", [])
        app_uuid = request.query_params.get("app_uuid")
        channel_uuid = request.query_params.get("channel_uuid")

        if app_uuid is None:
            raise ValidationError({"app_uuid": "Missing app_uuid in params."})

        if channel_uuid is None:
            raise ValidationError({"channel_uuid": "Missing channel_uuid in params."})

        agent = self.get_agent(agent_uuid)

        self.check_object_permissions(request, agent)

        use_case = AssignAgentUseCase()
        integrated_agent = use_case.execute(
            agent, project_uuid, app_uuid, channel_uuid, credentials, include_templates
        )

        response_serializer = ReadIntegratedAgentSerializer(integrated_agent)

        return Response(response_serializer.data, status=status.HTTP_201_CREATED)


class UnassignAgentView(GenericIntegratedAgentView):
    permission_classes = [IsAuthenticated, IsAgentOficialOrFromProjet]

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        project_uuid = get_project_uuid_from_request(request)
        agent = self.get_agent(agent_uuid)

        self.check_object_permissions(request, agent)

        use_case = UnassignAgentUseCase()
        use_case.execute(agent, project_uuid)

        return Response(status=status.HTTP_204_NO_CONTENT)


class IntegratedAgentViewSet(ViewSet):
    permission_classes = [AllowAny, IsIntegratedAgentFromProject]

    def retrieve(self, request: Request, pk: UUID, *args, **kwargs) -> Response:
        get_project_uuid_from_request(request)
        use_case = RetrieveIntegratedAgentUseCase()
        integrated_agent = use_case.execute(pk)

        self.check_object_permissions(request, integrated_agent)

        response_serializer = ReadIntegratedAgentSerializer(integrated_agent)

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def list(self, request: Request, *args, **kwargs) -> Response:
        project_uuid = get_project_uuid_from_request(request)

        use_case = ListIntegratedAgentUseCase()
        integrated_agents = use_case.execute(project_uuid)

        response_serializer = ReadIntegratedAgentSerializer(
            integrated_agents, many=True
        )

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request: Request, pk: UUID, *args, **kwargs) -> Response:
        get_project_uuid_from_request(request)

        request_serializer = UpdateIntegratedAgentSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        serialized_data: UpdateIntegratedAgentData = request_serializer.data

        use_case = UpdateIntegratedAgentUseCase()
        integrated_agent = use_case.execute(pk, serialized_data)

        response_serializer = ReadIntegratedAgentSerializer(integrated_agent)

        return Response(response_serializer.data, status=status.HTTP_200_OK)
