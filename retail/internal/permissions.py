from typing import Optional

from enum import IntEnum

from rest_framework import permissions
from rest_framework.request import Request

from retail.services.connect import ConnectService
from retail.interfaces.services.connect import ConnectServiceInterface


class CanCommunicateInternally(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated:
            return False

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
    """
    Permission class that verifies if a user has project-level permissions.

    This permission supports two types of users:

    1. **Internal Users** (with 'authentication.can_communicate_internally' permission):
       - Can query permissions for other users by providing 'user_email' in query params
       - Uses internal system authentication with Connect API
       - Request format: Header 'Project-Uuid' + Query param 'user_email'

    2. **Regular Users** (without internal permission):
       - Can only query their own permissions
       - Uses their JWT token for authentication with Connect API
       - Request format: Header 'Project-Uuid' + Authorization header with JWT

    The permission is granted if the user has 'contributor' or 'moderator' role
    in the specified project according to Connect microservice.

    Args:
        connect_service: Optional ConnectServiceInterface implementation for testing

    Returns:
        bool: True if user has contributor/moderator permissions, False otherwise

    Raises:
        No exceptions - returns False for any authentication/authorization failures
    """

    def __init__(self, connect_service: Optional[ConnectServiceInterface] = None):
        self.connect_service = connect_service or ConnectService()

    def has_permission(self, request: Request, view):
        project_uuid = request.headers.get("Project-Uuid")
        user = request.user

        if project_uuid is None or not user.is_authenticated:
            return False

        is_internal_user = user.has_perm("auth.can_communicate_internally")

        if is_internal_user:
            user_email = request.query_params.get("user_email")
            if user_email is None:
                return False

            status_code, response = self.connect_service.get_user_permissions(
                project_uuid, user_email
            )
        else:
            auth_header = request.META.get("HTTP_AUTHORIZATION", "")
            if not auth_header.startswith("Bearer "):
                return False

            user_token = auth_header.replace("Bearer ", "")
            user_email = user.email

            status_code, response = self.connect_service.get_user_permissions(
                project_uuid, user_email, user_token
            )

        if status_code != 200:
            return False

        project_authorization = response["project_authorization"]

        return project_authorization in (
            PermissionsLevels.contributor,
            PermissionsLevels.moderator,
        )
