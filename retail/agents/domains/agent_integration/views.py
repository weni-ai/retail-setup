import logging
from typing import cast
from uuid import UUID

from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.viewsets import ViewSet

from retail.agents.domains.agent_management.models import Agent
from retail.agents.shared.permissions import (
    IsAgentOficialOrFromProjet,
    IsIntegratedAgentFromProject,
)
from retail.agents.domains.agent_integration.serializers import (
    ReadIntegratedAgentSerializer,
    UpdateIntegratedAgentSerializer,
    RetrieveIntegratedAgentQueryParamsSerializer,
    DeliveredOrderTrackingEnableSerializer,
    PaymentRecoveryHookConfigSerializer,
    PaymentRecoveryHookConfigReadSerializer,
    TemplateLanguageSerializer,
)
from retail.agents.domains.agent_integration.utils import TEMPLATE_LANGUAGES
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
    UpdateIntegratedAgentData,
)
from retail.agents.domains.agent_integration.usecases.delivered_order_tracking import (
    DeliveredOrderTrackingConfigUseCase,
    DeliveredOrderTrackingWebhookUseCase,
)
from retail.agents.tasks import (
    task_delivered_order_tracking_webhook,
    task_payment_recovery_webhook,
)
from retail.agents.domains.agent_integration.usecases.payment_recovery import (
    PaymentRecoveryWebhookUseCase,
)
from retail.agents.domains.agent_integration.usecases.payment_recovery_hook_config import (
    PaymentRecoveryHookConfigUseCase,
)

from retail.internal.permissions import HasProjectPermission

logger = logging.getLogger(__name__)


class GenericIntegratedAgentView(APIView):
    def get_agent(self, agent_uuid: UUID) -> Agent:
        try:
            return Agent.objects.get(uuid=agent_uuid)
        except Agent.DoesNotExist:
            raise NotFound(f"Agent not found: {agent_uuid}")


class TemplateLanguagesView(APIView):
    """View to list available template languages for agent integration."""

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        """
        List all available template languages.

        Returns a list of languages with their Meta codes and display names.
        The frontend should display the display_name to users and send
        the code value when assigning an agent.
        """
        languages = TEMPLATE_LANGUAGES
        serializer = TemplateLanguageSerializer(languages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class AssignAgentView(GenericIntegratedAgentView):
    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsAgentOficialOrFromProjet,
    ]

    def post(self, request: Request, agent_uuid: UUID) -> Response:
        project_uuid = request.headers.get("Project-Uuid")
        app_uuid = request.query_params.get("app_uuid")
        channel_uuid = request.query_params.get("channel_uuid")

        if app_uuid is None:
            raise ValidationError({"app_uuid": "Missing app_uuid in params."})

        if channel_uuid is None:
            raise ValidationError({"channel_uuid": "Missing channel_uuid in params."})

        credentials = request.data.get("credentials", {})
        include_templates = request.data.get("templates", [])

        agent = self.get_agent(agent_uuid)

        self.check_object_permissions(request, agent)

        use_case = AssignAgentUseCase()
        integrated_agent = use_case.execute(
            agent=agent,
            project_uuid=project_uuid,
            app_uuid=app_uuid,
            channel_uuid=channel_uuid,
            credentials=credentials,
            include_templates=include_templates,
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

        # Use validated_data instead of .data to get only the fields that were actually sent
        serialized_data: UpdateIntegratedAgentData = request_serializer.validated_data

        use_case = UpdateIntegratedAgentUseCase()
        integrated_agent = use_case.get_integrated_agent(pk)

        self.check_object_permissions(request, integrated_agent)

        updated_integrated_agent = use_case.execute(integrated_agent, serialized_data)

        response_serializer = ReadIntegratedAgentSerializer(updated_integrated_agent)

        return Response(response_serializer.data, status=status.HTTP_200_OK)


class DeliveredOrderTrackingConfigView(APIView):
    """View for managing delivered order tracking configuration."""

    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsIntegratedAgentFromProject,
    ]

    def get(self, request: Request, pk: UUID) -> Response:
        """Get delivered order tracking configuration for an integrated agent."""
        use_case = DeliveredOrderTrackingConfigUseCase()

        # Get integrated agent (use case handles NotFound exception)
        integrated_agent = use_case.get_integrated_agent(pk)

        # Check permissions
        self.check_object_permissions(request, integrated_agent)

        # Get configuration (use case handles business logic)
        config_data = use_case.get_tracking_config(integrated_agent)

        return Response(config_data, status=status.HTTP_200_OK)


class DeliveredOrderTrackingEnableView(APIView):
    """View for enabling delivered order tracking."""

    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsIntegratedAgentFromProject,
    ]

    def post(self, request: Request, pk: UUID) -> Response:
        """Enable delivered order tracking for an integrated agent."""
        use_case = DeliveredOrderTrackingConfigUseCase()

        try:
            # Get integrated agent (use case handles NotFound exception)
            integrated_agent = use_case.get_integrated_agent(pk)

            # Check permissions
            self.check_object_permissions(request, integrated_agent)

            # Validate request data using serializer
            serializer = DeliveredOrderTrackingEnableSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)

            # Enable tracking (use case handles business logic)
            config_data = use_case.enable_tracking(
                integrated_agent,
                serializer.validated_data["vtex_app_key"],
                serializer.validated_data["vtex_app_token"],
            )

            return Response(config_data, status=status.HTTP_200_OK)

        except ValidationError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.exception(
                f"Unexpected error enabling delivered order tracking for agent {pk}: {e}"
            )
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeliveredOrderTrackingDisableView(APIView):
    """View for disabling delivered order tracking."""

    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsIntegratedAgentFromProject,
    ]

    def post(self, request: Request, pk: UUID) -> Response:
        """Disable delivered order tracking for an integrated agent."""
        use_case = DeliveredOrderTrackingConfigUseCase()

        try:
            # Get integrated agent (use case handles NotFound exception)
            integrated_agent = use_case.get_integrated_agent(pk)

            # Check permissions
            self.check_object_permissions(request, integrated_agent)

            # Disable tracking (use case handles business logic)
            config_data = use_case.disable_tracking(integrated_agent)

            return Response(config_data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception(
                f"Unexpected error disabling delivered order tracking for agent {pk}: {e}"
            )
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class DeliveredOrderTrackingWebhookView(APIView):
    """Webhook view for receiving VTEX delivered order tracking notifications."""

    permission_classes = [AllowAny]  # VTEX call this webhook

    def post(self, request: Request, pk: UUID) -> Response:
        """
        Receive delivered order tracking notification from VTEX.

        Args:
            request: HTTP request containing VTEX webhook data
            pk: UUID of the integrated agent

        Returns:
            HTTP response confirming receipt
        """
        # Check if this is a VTEX ping request
        if request.data.get("hookConfig") == "ping":
            logger.info(
                f"VTEX ping received for delivered order tracking webhook - agent {pk}"
            )
            return Response({"message": "Webhook available"}, status=status.HTTP_200_OK)

        # For actual webhook notifications, process asynchronously
        try:
            webhook_use_case = DeliveredOrderTrackingWebhookUseCase()
            try:
                webhook_use_case.get_integrated_agent(str(pk))
            except NotFound:
                logger.warning(
                    f"[DELIVERED_TRACKING] Integrated agent not found or inactive - "
                    f"agent={pk}"
                )
                return Response(
                    {"message": "Webhook received"}, status=status.HTTP_200_OK
                )

            task_delivered_order_tracking_webhook.apply_async(
                args=[pk, request.data],
                queue="vtex-io-orders-update-events",
            )

            logger.info(
                f"Delivered order tracking webhook queued for processing - agent {pk}"
            )
            return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception(
                f"Error queuing delivered order tracking webhook for agent {pk}: {e}"
            )

            return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)


class PaymentRecoveryHookConfigView(APIView):
    """View for managing payment recovery VTEX hook filter configuration."""

    permission_classes = [
        IsAuthenticated,
        HasProjectPermission,
        IsIntegratedAgentFromProject,
    ]

    def get(self, request: Request, pk: UUID) -> Response:
        """Get payment recovery hook configuration for an integrated agent."""
        use_case = PaymentRecoveryHookConfigUseCase()
        integrated_agent = use_case.get_integrated_agent(pk)
        self.check_object_permissions(request, integrated_agent)

        config_data = use_case.get_hook_config(integrated_agent)
        serializer = PaymentRecoveryHookConfigReadSerializer(config_data)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request: Request, pk: UUID) -> Response:
        """Update payment recovery sales channel filter and sync VTEX hook."""
        use_case = PaymentRecoveryHookConfigUseCase()
        integrated_agent = use_case.get_integrated_agent(pk)
        self.check_object_permissions(request, integrated_agent)

        serializer = PaymentRecoveryHookConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        config_data = use_case.update_sales_channels(
            integrated_agent,
            serializer.validated_data["sales_channels"],
        )
        response_serializer = PaymentRecoveryHookConfigReadSerializer(config_data)
        return Response(response_serializer.data, status=status.HTTP_200_OK)


class PaymentRecoveryWebhookView(APIView):
    """Webhook endpoint for receiving VTEX payment recovery notifications."""

    permission_classes = [AllowAny]

    def get(self, request: Request, pk: UUID) -> Response:
        logger.info(f"[PaymentRecovery] Health check received - agent={pk}")
        return Response({"message": "Webhook available"}, status=status.HTTP_200_OK)

    def post(self, request: Request, pk: UUID) -> Response:
        if request.data.get("hookConfig") == "ping":
            logger.info(f"[PaymentRecovery] VTEX ping received - agent={pk}")
            return Response({"message": "Webhook available"}, status=status.HTTP_200_OK)

        try:
            use_case = PaymentRecoveryWebhookUseCase()
            try:
                integrated_agent = use_case.get_integrated_agent(pk)
            except NotFound:
                logger.warning(
                    f"[PaymentRecovery] Integrated agent not found or inactive - "
                    f"agent={pk}"
                )
                return Response(
                    {"message": "Webhook received"}, status=status.HTTP_200_OK
                )

            countdown = use_case.get_delay_seconds(
                pk, integrated_agent=integrated_agent
            )

            task_payment_recovery_webhook.apply_async(
                args=[pk, request.data],
                countdown=countdown,
                queue="vtex-io-orders-update-events",
            )

            logger.info(
                f"[PaymentRecovery] Webhook scheduled for processing - "
                f"agent={pk} countdown={countdown}s"
            )
            return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.exception(
                f"[PaymentRecovery] Error queuing webhook - agent={pk}: {e}"
            )
            return Response({"message": "Webhook received"}, status=status.HTTP_200_OK)
