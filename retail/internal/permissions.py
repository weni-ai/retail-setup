from rest_framework import permissions


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
