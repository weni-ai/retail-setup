import json

from typing import cast

from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from retail.agents.models import Agent
from retail.agents.permissions import (
    IsAgentOficialOrFromProjet,
    IsIntegratedAgentFromProject,
)
from retail.agents.serializers import (
    PushAgentSerializer,
    ReadAgentSerializer,
    ReadIntegratedAgentSerializer,
    UpdateIntegratedAgentSerializer,
    RetrieveIntegratedAgentQueryParamsSerializer,
)
from retail.agents.tasks import validate_pre_approved_templates
from retail.agents.usecases import (
    AssignAgentUseCase,
    ListAgentsUseCase,
    PushAgentData,
    PushAgentUseCase,
    RetrieveAgentUseCase,
    UnassignAgentUseCase,
    RetrieveIntegratedAgentUseCase,
    RetrieveIntegratedAgentQueryParams,
    ListIntegratedAgentUseCase,
    UpdateIntegratedAgentUseCase,
    UpdateIntegratedAgentData,
)
from retail.vtex.tasks import task_order_status_agent_webhook


def get_project_uuid_from_request(request: Request) -> str:
    project_uuid = request.headers.get("Project-Uuid")
    if project_uuid is None:
        raise ValidationError({"project_uuid": "Missing project uuid in header."})

    return project_uuid


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
        print("AssignAgentView")

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

        print("Agente encontrado")

        self.check_object_permissions(request, agent)

        print("Entrando no use case")

        use_case = AssignAgentUseCase()

        print("Executando use case")

        integrated_agent = use_case.execute(
            agent, project_uuid, app_uuid, channel_uuid, credentials, include_templates
        )

        print("Agente integrado criado")

        response_serializer = ReadIntegratedAgentSerializer(integrated_agent)

        print(f"Response serializer: {response_serializer.data}")

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


class AgentWebhookView(APIView):
    permission_classes = [AllowAny]

    def post(self, request: Request, webhook_uuid: UUID, *args, **kwargs) -> Response:
        # Ignoring specific UUID: d30bcce8-ce67-4677-8a33-c12b62a51d4f
        if str(webhook_uuid) != "d30bcce8-ce67-4677-8a33-c12b62a51d4f":
            task_order_status_agent_webhook.apply_async(
                args=[webhook_uuid, request.data, request.query_params],
                queue="vtex-io-orders-update-events",
            )

        return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)


class IntegratedAgentViewSet(ViewSet):
    permission_classes = [AllowAny, IsIntegratedAgentFromProject]

    def retrieve(self, request: Request, pk: UUID, *args, **kwargs) -> Response:
        get_project_uuid_from_request(request)

        query_params_serializer = RetrieveIntegratedAgentQueryParamsSerializer(
            data=request.query_params
        )
        query_params_serializer.is_valid(raise_exception=True)
        query_params_data = cast(
            RetrieveIntegratedAgentQueryParams, query_params_serializer.data
        )

        use_case = RetrieveIntegratedAgentUseCase()
        integrated_agent = use_case.execute(pk, query_params_data)

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
