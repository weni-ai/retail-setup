from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from retail.internal.views import InternalGenericViewSet
from retail.projects.models import Project


class ProjectViewSet(viewsets.ViewSet, InternalGenericViewSet):
    permission_classes = [IsAuthenticated]

    def list(self, request):
        projects = []
        for project in Project.objects.all():

            projects_data = {
                "name": project.name,
                "uuid": project.uuid,
                "organization_name": project.organization_name,
            }

            projects.append(projects_data)

        return Response(projects)
