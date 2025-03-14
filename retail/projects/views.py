from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework import status

from retail.internal.views import InternalGenericViewSet
from retail.projects.models import Project
from retail.internal.permissions import CanCommunicateInternally
from retail.projects.serializer import ProjectVtexConfigSerializer
from retail.projects.usecases.project_vtex import ProjectVtexConfigUseCase


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
