from unittest.mock import Mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory
from weni_commons.auth import WeniAuthContext

from retail.agents.shared.permissions import (
    IsAgentOficialOrFromProjet,
    IsAgentOficialOrFromProjetByHeader,
    IsIntegratedAgentFromProject,
    IsIntegratedAgentFromProjectByHeader,
)

User = get_user_model()


class IsAgentOficialOrFromProjetTest(TestCase):
    """Auth-context variant: project scope comes from ``request.auth``."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsAgentOficialOrFromProjet()
        self.mock_view = Mock()

    def _request_with_project(self, project_uuid=None):
        request = Request(self.factory.get("/"))
        request.auth = WeniAuthContext(project_uuid=project_uuid, token_type="jwt")
        return request

    def test_oficial_agent_without_project_scope_is_denied(self):
        request = self._request_with_project(project_uuid=None)

        mock_obj = Mock()
        mock_obj.is_oficial = True
        mock_obj.project.uuid = "original-uuid"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_oficial_agent_with_project_scope_is_allowed(self):
        request = self._request_with_project(project_uuid="caller-uuid")

        mock_obj = Mock()
        mock_obj.is_oficial = True
        mock_obj.project.uuid = "different-uuid"

        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_matching_project_uuid_is_allowed(self):
        project_uuid = "test-uuid-123"
        request = self._request_with_project(project_uuid=project_uuid)

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = project_uuid

        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_non_matching_project_uuid_is_denied(self):
        request = self._request_with_project(project_uuid="different-uuid")

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = "original-uuid"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_missing_project_scope_is_denied(self):
        request = self._request_with_project(project_uuid=None)

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = "test-uuid-123"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_header_is_ignored_by_auth_variant(self):
        """The auth variant must not fall back to the request header."""
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID="header-uuid"))
        request.auth = WeniAuthContext(project_uuid=None, token_type="jwt")

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = "header-uuid"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )


class IsIntegratedAgentFromProjectTest(TestCase):
    """Auth-context variant: project scope comes from ``request.auth``."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsIntegratedAgentFromProject()
        self.mock_view = Mock()

    def _request_with_project(self, project_uuid=None):
        request = Request(self.factory.get("/"))
        request.auth = WeniAuthContext(project_uuid=project_uuid, token_type="jwt")
        return request

    def test_has_permission_with_project_scope_returns_true(self):
        request = self._request_with_project(project_uuid="test-uuid-123")

        self.assertTrue(self.permission.has_permission(request, self.mock_view))

    def test_has_permission_without_project_scope_returns_false(self):
        request = self._request_with_project(project_uuid=None)

        self.assertFalse(self.permission.has_permission(request, self.mock_view))

    def test_matching_project_uuid_is_allowed(self):
        project_uuid = "test-uuid-123"
        request = self._request_with_project(project_uuid=project_uuid)

        mock_obj = Mock()
        mock_obj.project.uuid = project_uuid

        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_non_matching_project_uuid_is_denied(self):
        request = self._request_with_project(project_uuid="different-uuid")

        mock_obj = Mock()
        mock_obj.project.uuid = "original-uuid"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_header_is_ignored_by_auth_variant(self):
        """The auth variant must not fall back to the request header."""
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID="header-uuid"))
        request.auth = WeniAuthContext(project_uuid=None, token_type="jwt")

        self.assertFalse(self.permission.has_permission(request, self.mock_view))


class IsAgentOficialOrFromProjetByHeaderTest(TestCase):
    """Header variant used by views not yet on the unified auth flow."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsAgentOficialOrFromProjetByHeader()
        self.mock_view = Mock()

    def test_oficial_agent_without_header_is_denied(self):
        request = Request(self.factory.get("/"))

        mock_obj = Mock()
        mock_obj.is_oficial = True
        mock_obj.project.uuid = "test-uuid-123"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_matching_project_uuid_header_is_allowed(self):
        project_uuid = "test-uuid-123"
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID=project_uuid))

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = project_uuid

        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_non_matching_project_uuid_header_is_denied(self):
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID="different-uuid"))

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = "original-uuid"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_missing_header_is_denied(self):
        request = Request(self.factory.get("/"))

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = "test-uuid-123"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_oficial_agent_with_different_project_header_is_allowed(self):
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID="different-uuid"))

        mock_obj = Mock()
        mock_obj.is_oficial = True
        mock_obj.project.uuid = "original-uuid"

        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )


class IsIntegratedAgentFromProjectByHeaderTest(TestCase):
    """Header variant used by views not yet on the unified auth flow."""

    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = IsIntegratedAgentFromProjectByHeader()
        self.mock_view = Mock()

    def test_has_permission_with_header_returns_true(self):
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID="test-uuid-123"))

        self.assertTrue(self.permission.has_permission(request, self.mock_view))

    def test_has_permission_without_header_returns_false(self):
        request = Request(self.factory.get("/"))

        self.assertFalse(self.permission.has_permission(request, self.mock_view))

    def test_matching_project_uuid_header_is_allowed(self):
        project_uuid = "test-uuid-123"
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID=project_uuid))

        mock_obj = Mock()
        mock_obj.project.uuid = project_uuid

        self.assertTrue(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_non_matching_project_uuid_header_is_denied(self):
        request = Request(self.factory.get("/", HTTP_PROJECT_UUID="different-uuid"))

        mock_obj = Mock()
        mock_obj.project.uuid = "original-uuid"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )

    def test_missing_header_is_denied(self):
        request = Request(self.factory.get("/"))

        mock_obj = Mock()
        mock_obj.project.uuid = "test-uuid-123"

        self.assertFalse(
            self.permission.has_object_permission(request, self.mock_view, mock_obj)
        )
