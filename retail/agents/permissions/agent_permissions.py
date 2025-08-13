from rest_framework.permissions import BasePermission


class IsAgentOficialOrFromProjet(BasePermission):
    def has_object_permission(self, request, view, obj):
        project_uuid = request.headers.get("Project-Uuid")

        if project_uuid is None:
            return False

        return obj.is_oficial or str(obj.project.uuid) == project_uuid
