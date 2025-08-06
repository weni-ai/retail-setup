from rest_framework import viewsets
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework import status

from retail.internal.views import InternalGenericViewSet
from retail.projects.models import Project
from retail.internal.permissions import CanCommunicateInternally
from retail.projects.serializer import ProjectVtexConfigSerializer
from retail.projects.usecases.get_project_vtex_account import (
    GetProjectVtexAccountUseCase,
)
from retail.projects.usecases.project_vtex import ProjectVtexConfigUseCase
from retail.utils.aws.lambda_validator import LambdaURLValidator


class ProjectViewSet(viewsets.ViewSet, InternalGenericViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        projects = []
        for project in Project.objects.all():
            projects_data = {
                "name": project.name,
                "uuid": project.uuid,
            }

            projects.append(projects_data)

        return Response(projects)


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


class VtexAccountLookupView(APIView, LambdaURLValidator):
    """
    API view to look up the VTEX account associated with a given project.

    This view handles GET requests to retrieve the VTEX account information
    for a specified project UUID. If the VTEX account is not found, it returns
    a 400 Bad Request response with an appropriate message.
    """

    authentication_classes = []

    def get(self, request, project_uuid):
        """
        Handle GET request to retrieve VTEX account for a project.

        Args:
            request: The HTTP request object.
            project_uuid: The UUID of the project for which to retrieve the VTEX account.

        Returns:
            Response: A Response object containing the VTEX account information
            or an error message if the account is not found.
        """
        validation_response = self._validate_lambda_url(request)
        if validation_response:
            return validation_response

        use_case = GetProjectVtexAccountUseCase()
        vtex_account = use_case.execute(project_uuid)

        if not vtex_account:
            return Response(
                {"detail": "VTEX account not found for this project."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"vtex_account": vtex_account})

    def _validate_lambda_url(self, request):
        validation_response = self.protected_resource(request)
        if validation_response.status_code != 200:
            return validation_response
        return None
