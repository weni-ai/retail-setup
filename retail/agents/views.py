import json
from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from retail.agents.models import Agent
from retail.agents.permissions import IsAgentOficialOrFromProjet
from retail.agents.serializers import (
    AgentWebhookSerializer,
    PushAgentSerializer,
    ReadAgentSerializer,
    ReadIntegratedAgentSerializer,
)
from retail.agents.tasks import validate_pre_approved_templates
from retail.agents.usecases import (
    AgentWebhookData,
    AgentWebhookUseCase,
    AssignAgentUseCase,
    ListAgentsUseCase,
    PushAgentData,
    PushAgentUseCase,
    RetrieveAgentUseCase,
    UnassignAgentUseCase,
)
from retail.interfaces.clients.aws_lambda.client import RequestData


def get_project_uuid_from_request(request: Request) -> str:
    project_uuid = request.headers.get("Project-Uuid")

    if project_uuid is None:
        raise ValidationError({"project_uuid": "Missing project uuid in header."})

    return project_uuid


class PushAgentView(APIView):
    permission_classes = [IsAuthenticated]

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
        project_uuid = get_project_uuid_from_request(request)

        agents = ListAgentsUseCase.execute(project_uuid)

        response_serializer = ReadAgentSerializer(agents, many=True)

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def retrieve(self, request: Request, pk=None, *args, **kwargs) -> Response:
        get_project_uuid_from_request(request)

        agent = RetrieveAgentUseCase.execute(pk)

        self.check_object_permissions(request, agent)

        response_serializer = ReadAgentSerializer(agent)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class GenericIntegratedAgentView(APIView):
    def get_agent(self, agent_uuid: UUID) -> Agent:
        try:
            return Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            raise NotFound(f"Agent not found: {agent_uuid}")


class AssignAgentView(GenericIntegratedAgentView):
    permission_classes = [IsAuthenticated, IsAgentOficialOrFromProjet]

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        project_uuid = get_project_uuid_from_request(request)
        agent = self.get_agent(agent_uuid)

        self.check_object_permissions(request, agent)

        use_case = AssignAgentUseCase()

        integrated_agent, raw_client_secret = use_case.execute(agent, project_uuid)

        response_serializer = ReadIntegratedAgentSerializer(
            integrated_agent, show_client_secret=True
        )

        data = dict(response_serializer.data)
        data["client_secret"] = raw_client_secret

        return Response(data, status=status.HTTP_201_CREATED)


class UnassignAgentView(GenericIntegratedAgentView):
    permission_classes = [IsAuthenticated, IsAgentOficialOrFromProjet]

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        project_uuid = get_project_uuid_from_request(request)
        agent = self.get_agent(agent_uuid)

        self.check_object_permissions(request, agent)

        use_case = UnassignAgentUseCase()
        use_case.execute(agent, project_uuid)

        return Response(status=status.HTTP_204_NO_CONTENT)


class AgentWebhookView(APIView):
    def _get_data_from_request(self, request: Request) -> RequestData:
        request_params = request.query_params
        request_params.pop("client_secret")

        return RequestData(
            params=request_params,
            payload=request.data,
            credentials={},  # TODO: Set credentials in usecase
        )

    def post(self, request: Request, webhook_uuid: UUID, *args, **kwargs) -> Response:
        data = AgentWebhookData(
            client_secret=request.query_params.get("client_secret"),
            webhook_uuid=webhook_uuid,
        )

        request_serializer = AgentWebhookSerializer(data=data)
        request_serializer.is_valid(raise_exception=True)

        request_data = self._get_data_from_request(request)

        use_case = AgentWebhookUseCase()
        lambda_return = use_case.execute(request_serializer.data, request_data)

        return Response(lambda_return, status=status.HTTP_200_OK)
