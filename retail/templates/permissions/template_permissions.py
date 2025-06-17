from rest_framework.permissions import BasePermission


class IsTemplateFromUserProject(BasePermission):
    def has_object_permission(self, request, view, obj):
        project_uuid = request.headers.get("Project-Uuid")

        if project_uuid is None:
            return False

        if obj.integrated_agent is None:
            return False

        return str(obj.integrated_agent.project.uuid) == project_uuid
