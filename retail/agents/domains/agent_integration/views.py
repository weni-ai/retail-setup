from typing import cast

from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.shared.permissions import (
    IsAgentOficialOrFromProjet,
    IsIntegratedAgentFromProject,
)
from retail.agents.domains.agent_integration.serializers import (
    ReadIntegratedAgentSerializer,
    UpdateIntegratedAgentSerializer,
    RetrieveIntegratedAgentQueryParamsSerializer,
)
from retail.agents.domains.agent_integration.usecases.assign import AssignAgentUseCase
from retail.agents.domains.agent_integration.usecases.list import (
    ListIntegratedAgentUseCase,
)
from retail.agents.domains.agent_integration.usecases.retrieve import (
    RetrieveIntegratedAgentUseCase,
)
from retail.agents.domains.agent_integration.usecases.unassign import (
    UnassignAgentUseCase,
)
from retail.agents.domains.agent_integration.usecases.update import (
    UpdateIntegratedAgentUseCase,
)
from retail.agents.domains.agent_integration.usecases.update import (
    UpdateIntegratedAgentData,
)
from retail.agents.domains.agent_integration.usecases.dev_environment import (
    DevEnvironmentConfigUseCase,
    DevEnvironmentRunUseCase,
)

from retail.internal.permissions import HasProjectPermission


class GenericIntegratedAgentView(APIView):
    def get_agent(self, agent_uuid: UUID) -> Agent:
        try:
            return Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            raise NotFound(f"Agent not found: {agent_uuid}")


class AssignAgentView(GenericIntegratedAgentView):
    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsAgentOficialOrFromProjet,
    ]

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        project_uuid = request.headers.get("Project-Uuid")
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
    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsAgentOficialOrFromProjet,
    ]

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        project_uuid = request.headers.get("Project-Uuid")
        agent = self.get_agent(agent_uuid)

        self.check_object_permissions(request, agent)

        use_case = UnassignAgentUseCase()
        use_case.execute(agent, project_uuid)

        return Response(status=status.HTTP_204_NO_CONTENT)


class IntegratedAgentViewSet(ViewSet):
    permission_classes = [IsAuthenticated, IsIntegratedAgentFromProject]

    def get_permissions(self):
        permissions = super().get_permissions()

        if self.action == "partial_update":
            permissions.append(HasProjectPermission())

        return permissions

    def retrieve(self, request: Request, pk: UUID, *args, **kwargs) -> Response:
        query_params_serializer = RetrieveIntegratedAgentQueryParamsSerializer(
            data=request.query_params
        )
        query_params_serializer.is_valid(raise_exception=True)
        query_params_data = cast(
            RetrieveIntegratedAgentQueryParamsSerializer, query_params_serializer.data
        )

        use_case = RetrieveIntegratedAgentUseCase()
        integrated_agent = use_case.execute(pk, query_params_data)

        self.check_object_permissions(request, integrated_agent)

        response_serializer = ReadIntegratedAgentSerializer(integrated_agent)

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def list(self, request: Request, *args, **kwargs) -> Response:
        project_uuid = request.headers.get("Project-Uuid")

        use_case = ListIntegratedAgentUseCase()
        integrated_agents = use_case.execute(project_uuid)

        response_serializer = ReadIntegratedAgentSerializer(
            integrated_agents, many=True
        )

        return Response(response_serializer.data, status=status.HTTP_200_OK)

    def partial_update(self, request: Request, pk: UUID, *args, **kwargs) -> Response:
        request_serializer = UpdateIntegratedAgentSerializer(data=request.data)
        request_serializer.is_valid(raise_exception=True)

        serialized_data: UpdateIntegratedAgentData = request_serializer.data

        use_case = UpdateIntegratedAgentUseCase()
        integrated_agent = use_case.get_integrated_agent(pk)

        self.check_object_permissions(request, integrated_agent)

        updated_integrated_agent = use_case.execute(integrated_agent, serialized_data)

        response_serializer = ReadIntegratedAgentSerializer(updated_integrated_agent)

        return Response(response_serializer.data, status=status.HTTP_200_OK)


class DevEnvironmentConfigView(APIView):
    """View for managing development environment configuration."""

    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsIntegratedAgentFromProject,
    ]

    def get(self, request: Request, pk: UUID) -> Response:
        """Get test environment configuration for an integrated agent."""
        use_case = DevEnvironmentConfigUseCase()

        try:
            integrated_agent = use_case.get_integrated_agent(pk)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {pk}")

        self.check_object_permissions(request, integrated_agent)

        config_data = use_case.get_dev_config(integrated_agent)
        return Response(config_data, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: UUID) -> Response:
        """Update test environment configuration for an integrated agent."""
        use_case = DevEnvironmentConfigUseCase()

        try:
            integrated_agent = use_case.get_integrated_agent(pk)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {pk}")

        self.check_object_permissions(request, integrated_agent)

        try:
            config_data = use_case.update_dev_config(integrated_agent, request.data)
            return Response(config_data, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class DevEnvironmentRunView(APIView):
    """View for running development environment."""

    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsIntegratedAgentFromProject,
    ]

    def post(self, request: Request, pk: UUID) -> Response:
        """Run test environment with configured phone numbers."""
        use_case = DevEnvironmentRunUseCase()
        config_use_case = DevEnvironmentConfigUseCase()

        try:
            integrated_agent = config_use_case.get_integrated_agent(pk)
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Integrated agent not found: {pk}")

        self.check_object_permissions(request, integrated_agent)

        try:
            # Use request data if provided, otherwise empty dict
            dev_data = request.data if request.data else {}
            result = use_case.run_dev_environment(integrated_agent, dev_data)
            return Response(result, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response(
                {"error": f"Internal server error: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
