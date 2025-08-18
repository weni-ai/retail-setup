from unittest.mock import Mock
from django.test import TestCase
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate
from django.contrib.auth import get_user_model

from retail.agents.shared.permissions import (
    IsAgentOficialOrFromProjet,
    IsIntegratedAgentFromProject,
)

User = get_user_model()


class IsAgentOficialOrFromProjetTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.permission = IsAgentOficialOrFromProjet()
        self.mock_view = Mock()

    def _make_drf_request(self, django_request, user=None):
        if user:
            force_authenticate(django_request, user=user)
        return Request(django_request)

    def test_has_object_permission_with_oficial_agent_returns_false(self):
        django_request = self.factory.get("/")
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.is_oficial = True
        mock_obj.project.uuid = "test-uuid-123"

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertFalse(result)

    def test_has_object_permission_with_oficial_agent_and_no_project_uuid_returns_false(
        self,
    ):
        django_request = self.factory.get("/")
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.is_oficial = True
        mock_obj.project.uuid = "test-uuid-123"

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertFalse(result)

    def test_has_object_permission_with_matching_project_uuid_returns_false(self):
        project_uuid = "test-uuid-123"
        django_request = self.factory.get("/", HTTP_PROJECT_UUID=project_uuid)
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = project_uuid

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertTrue(result)

    def test_has_object_permission_with_non_matching_project_uuid_returns_false(self):
        django_request = self.factory.get("/", HTTP_PROJECT_UUID="different-uuid")
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = "original-uuid"

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertFalse(result)

    def test_has_object_permission_without_project_uuid_returns_false(self):
        django_request = self.factory.get("/")
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.is_oficial = False
        mock_obj.project.uuid = "test-uuid-123"

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertFalse(result)

    def test_has_object_permission_with_oficial_agent_and_different_project_uuid_returns_true(
        self,
    ):
        django_request = self.factory.get("/", HTTP_PROJECT_UUID="different-uuid")
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.is_oficial = True
        mock_obj.project.uuid = "original-uuid"

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertTrue(result)


class IsIntegratedAgentFromProjectTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.permission = IsIntegratedAgentFromProject()
        self.mock_view = Mock()

    def _make_drf_request(self, django_request, user=None):
        if user:
            force_authenticate(django_request, user=user)
        return Request(django_request)

    def test_has_permission_with_project_uuid_returns_true(self):
        django_request = self.factory.get("/", HTTP_PROJECT_UUID="test-uuid-123")
        request = self._make_drf_request(django_request, user=self.user)

        result = self.permission.has_permission(request, self.mock_view)

        self.assertTrue(result)

    def test_has_permission_without_project_uuid_returns_false(self):
        django_request = self.factory.get("/")
        request = self._make_drf_request(django_request, user=self.user)

        result = self.permission.has_permission(request, self.mock_view)

        self.assertFalse(result)

    def test_has_object_permission_with_matching_project_uuid_returns_true(self):
        project_uuid = "test-uuid-123"
        django_request = self.factory.get("/", HTTP_PROJECT_UUID=project_uuid)
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.project.uuid = project_uuid

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertTrue(result)

    def test_has_object_permission_with_non_matching_project_uuid_returns_false(self):
        django_request = self.factory.get("/", HTTP_PROJECT_UUID="different-uuid")
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.project.uuid = "original-uuid"

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertFalse(result)

    def test_has_object_permission_without_project_uuid_returns_false(self):
        django_request = self.factory.get("/")
        request = self._make_drf_request(django_request, user=self.user)

        mock_obj = Mock()
        mock_obj.project.uuid = "test-uuid-123"

        result = self.permission.has_object_permission(
            request, self.mock_view, mock_obj
        )

        self.assertFalse(result)
