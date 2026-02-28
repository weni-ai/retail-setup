import logging

from rest_framework import viewsets, mixins
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework import status

from retail.internal.jwt_mixins import JWTModuleAuthMixin
from retail.internal.views import InternalGenericViewSet, KeycloakAPIView
from retail.projects.models import Project, ProjectOnboarding
from retail.internal.permissions import CanCommunicateInternally
from retail.projects.serializer import (
    ProjectSerializer,
    ProjectVtexConfigSerializer,
    StartOnboardingSerializer,
    CrawlerWebhookSerializer,
    OnboardingPatchSerializer,
    ProjectOnboardingSerializer,
)
from retail.projects.usecases.get_project_vtex_account import (
    GetProjectVtexAccountUseCase,
)
from retail.projects.usecases.onboarding_dto import (
    StartOnboardingDTO,
    CrawlerWebhookDTO,
)
from retail.projects.usecases.project_vtex import ProjectVtexConfigUseCase
from retail.projects.usecases.start_crawl import CrawlerStartError
from retail.projects.usecases.start_onboarding import StartOnboardingUseCase
from retail.projects.usecases.update_onboarding_progress import (
    UpdateOnboardingProgressUseCase,
)

logger = logging.getLogger(__name__)


class ProjectViewSet(mixins.ListModelMixin, InternalGenericViewSet):
    permission_classes = [IsAuthenticated]
    serializer_class = ProjectSerializer

    queryset = Project.objects.all()


class ProjectVtexViewSet(viewsets.ViewSet):
    """ViewSet responsible for managing VTEX-related configurations in projects."""

    permission_classes = [CanCommunicateInternally]
    lookup_field = "uuid"
    lookup_url_kwarg = "uuid"

    @action(detail=True, methods=["POST"], url_path="set-vtex-store-type")
    def set_vtex_store_type(self, request, uuid=None):
        """Adds or updates the VTEX store type in the project config."""
        serializer = ProjectVtexConfigSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        vtex_store_type = serializer.validated_data["vtex_store_type"]

        try:
            result = ProjectVtexConfigUseCase.set_store_type(
                project_uuid=uuid, vtex_store_type=vtex_store_type
            )
            return Response(result, status=status.HTTP_200_OK)
        except ValidationError as e:
            return Response(e.detail, status=status.HTTP_400_BAD_REQUEST)


class VtexAccountLookupView(JWTModuleAuthMixin, APIView):
    """
    API view to look up the VTEX account associated with a given project.

    This view handles GET requests to retrieve the VTEX account information
    for a specified project UUID. If the VTEX account is not found, it returns
    a 400 Bad Request response with an appropriate message.
    """

    def get(self, request):
        """
        Handle GET request to retrieve VTEX account for a project.

        Args:
            request: The HTTP request object.

        Returns:
            Response: A Response object containing the VTEX account information
            or an error message if the account is not found.
        """
        use_case = GetProjectVtexAccountUseCase()
        vtex_account = use_case.execute(self.project_uuid)

        if not vtex_account:
            return Response(
                {"detail": "VTEX account not found for this project."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"vtex_account": vtex_account})


class StartOnboardingView(KeycloakAPIView):
    """
    Starts the onboarding crawl process for a store.

    If the project is already linked (via EDA), the crawl starts
    immediately. Otherwise, a background task is scheduled to
    wait for the project link before crawling.
    """

    def post(self, request, vtex_account: str) -> Response:
        """
        Starts or schedules the crawl for the given vtex_account.

        Expects:
            { "crawl_url": "https://www.wenipartner.com.br/" }
        """
        serializer = StartOnboardingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dto = StartOnboardingDTO(
            vtex_account=vtex_account,
            crawl_url=serializer.validated_data["crawl_url"],
            channel=serializer.validated_data["channel"],
        )

        try:
            StartOnboardingUseCase().execute(dto)
        except CrawlerStartError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_502_BAD_GATEWAY,
            )

        return Response({"status": "started"}, status=status.HTTP_201_CREATED)


class CrawlerWebhookView(APIView):
    """
    Webhook endpoint called by the Crawler MS to report event-based
    progress on the store scraping process.

    Uses the project UUID as identifier since the project is guaranteed
    to be linked at this stage. Unauthenticated — the crawler calls it
    using the URL provided during the crawl start request.
    """

    permission_classes = []

    def post(self, request, onboarding_uuid) -> Response:
        """
        Receives event updates from the Crawler MS.
        """
        serializer = CrawlerWebhookSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        dto = CrawlerWebhookDTO(**serializer.validated_data)

        try:
            onboarding = UpdateOnboardingProgressUseCase.execute(
                str(onboarding_uuid), dto
            )
        except ProjectOnboarding.DoesNotExist:
            logger.warning(
                f"[CrawlerWebhook] No onboarding found for "
                f"onboarding_uuid={onboarding_uuid}"
            )
            return Response(
                {"detail": f"No onboarding found for: {onboarding_uuid}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(
            ProjectOnboardingSerializer(onboarding).data,
            status=status.HTTP_200_OK,
        )


class OnboardingStatusView(KeycloakAPIView):
    """
    Returns the current onboarding status for a store.
    Used by the front-end to poll progress across all steps.
    """

    def get(self, request, vtex_account: str) -> Response:
        onboarding, _created = ProjectOnboarding.objects.select_related(
            "project"
        ).get_or_create(
            vtex_account=vtex_account,
        )

        return Response(
            ProjectOnboardingSerializer(onboarding).data,
            status=status.HTTP_200_OK,
        )


class OnboardingPatchView(KeycloakAPIView):
    """
    Allows the front-end to partially update editable onboarding fields:
    ``completed`` and ``current_page``.
    """

    def patch(self, request, vtex_account: str) -> Response:
        """
        Partially updates the onboarding record.

        Accepts:
            { "completed": true, "current_page": "some_page" }
        """
        try:
            onboarding = ProjectOnboarding.objects.select_related("project").get(
                vtex_account=vtex_account,
            )
        except ProjectOnboarding.DoesNotExist:
            return Response(
                {"detail": "No onboarding found for this vtex_account."},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = OnboardingPatchSerializer(
            onboarding, data=request.data, partial=True
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response(
            ProjectOnboardingSerializer(onboarding).data,
            status=status.HTTP_200_OK,
        )
