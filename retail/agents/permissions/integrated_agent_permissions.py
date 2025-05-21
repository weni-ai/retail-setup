from rest_framework.permissions import BasePermission


class IsIntegratedAgentFromProject(BasePermission):
    def has_object_permission(self, request, view, obj):
        project_uuid = request.headers.get("Project-Uuid")
        return str(obj.project.uuid) == project_uuid
