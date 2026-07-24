from typing import Optional

from rest_framework.permissions import BasePermission
from rest_framework.request import Request
from weni_commons.auth import WeniAuthContext


def project_uuid_from_auth(request: Request) -> Optional[str]:
    """Return the project UUID carried by the unified auth context.

    ``WeniAuthentication`` populates ``request.auth`` with the project
    scope taken from the JWT (JWT callers) or from the standardized
    request locations (Keycloak callers). Migrated views trust this value
    exclusively and never read a raw request header.

    Args:
        request: The incoming DRF request.

    Returns:
        The project UUID, or ``None`` when it cannot be resolved.
    """
    auth = getattr(request, "auth", None)
    if isinstance(auth, WeniAuthContext) and auth.has_project_uuid:
        return auth.project_uuid

    return None


def project_uuid_from_header(request: Request) -> Optional[str]:
    """Return the project UUID from the legacy ``Project-Uuid`` header.

    Used only by views that are not yet migrated to the unified auth flow.
    Remove alongside the ``*ByHeader`` permission classes once every
    consumer reads the tenant from the auth context.

    Args:
        request: The incoming DRF request.

    Returns:
        The project UUID, or ``None`` when the header is absent.
    """
    return request.headers.get("Project-Uuid")


class _IsAgentOficialOrFromProjectBase(BasePermission):
    """Grant access to official agents or agents owned by the caller's project.

    Concrete subclasses define where the caller's project scope comes from
    by implementing ``_resolve_project_uuid``.
    """

    def _resolve_project_uuid(self, request: Request) -> Optional[str]:
        raise NotImplementedError

    def has_object_permission(self, request, view, obj) -> bool:
        project_uuid = self._resolve_project_uuid(request)

        if project_uuid is None:
            return False

        return obj.is_oficial or str(obj.project.uuid) == project_uuid


class _IsIntegratedAgentFromProjectBase(BasePermission):
    """Grant access when the integrated agent belongs to the caller's project.

    Concrete subclasses define where the caller's project scope comes from
    by implementing ``_resolve_project_uuid``.
    """

    def _resolve_project_uuid(self, request: Request) -> Optional[str]:
        raise NotImplementedError

    def has_permission(self, request, view) -> bool:
        return self._resolve_project_uuid(request) is not None

    def has_object_permission(self, request, view, obj) -> bool:
        project_uuid = self._resolve_project_uuid(request)

        if project_uuid is None:
            return False

        return str(obj.project.uuid) == project_uuid


class IsAgentOficialOrFromProjet(_IsAgentOficialOrFromProjectBase):
    """Auth-context variant: reads the project scope from ``request.auth``."""

    def _resolve_project_uuid(self, request: Request) -> Optional[str]:
        return project_uuid_from_auth(request)


class IsIntegratedAgentFromProject(_IsIntegratedAgentFromProjectBase):
    """Auth-context variant: reads the project scope from ``request.auth``."""

    def _resolve_project_uuid(self, request: Request) -> Optional[str]:
        return project_uuid_from_auth(request)


class IsAgentOficialOrFromProjetByHeader(_IsAgentOficialOrFromProjectBase):
    """Resolves the project scope from the ``Project-Uuid`` request header.

    Transitional: kept for views not yet on the unified auth flow. Delete
    once ``AgentViewSet`` reads the tenant from the auth context.
    """

    def _resolve_project_uuid(self, request: Request) -> Optional[str]:
        return project_uuid_from_header(request)


class IsIntegratedAgentFromProjectByHeader(_IsIntegratedAgentFromProjectBase):
    """Resolves the project scope from the ``Project-Uuid`` request header.

    Transitional: kept for views not yet on the unified auth flow. Delete
    once delivered-order-tracking and broadcast report views read the
    tenant from the auth context.
    """

    def _resolve_project_uuid(self, request: Request) -> Optional[str]:
        return project_uuid_from_header(request)
