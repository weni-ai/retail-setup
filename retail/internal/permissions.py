from typing import Optional

from enum import IntEnum

from rest_framework import permissions
from rest_framework.request import Request

from retail.services.connect import ConnectService
from retail.interfaces.services.connect import ConnectServiceInterface


class CanCommunicateInternally(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        # Check if the user is authenticated
        user = request.user
        if not user.is_authenticated:
            return False

        # Check if the user has 'can_communicate_internally' permission
        has_internal_permission = user.user_permissions.filter(
            codename="can_communicate_internally"
        ).exists()

        return has_internal_permission


class PermissionsLevels(IntEnum):
    not_configured = 0
    viewer = 1
    contributor = 2
    moderator = 3
    support = 4
    chat_user = 5


class HasProjectPermission(permissions.BasePermission):
    def __init__(self, connect_service: Optional[ConnectServiceInterface] = None):
        self.connect_service = connect_service or ConnectService()

    def has_permission(self, request: Request, view):
        project_uuid = request.headers.get("Project-Uuid")
        user_email = request.query_params.get("user_email")

        if project_uuid is None or user_email is None:
            return False

        status_code, response = self.connect_service.get_user_permissions(
            project_uuid, user_email
        )

        print(status_code, response)

        if status_code != 200:
            return False

        project_authorization = response["project_authorization"]

        return project_authorization in (
            PermissionsLevels.contributor,
            PermissionsLevels.moderator,
        )
