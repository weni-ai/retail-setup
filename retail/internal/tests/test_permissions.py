from unittest.mock import Mock
from uuid import uuid4

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory, force_authenticate
from weni_commons.auth import WeniAuthContext

from retail.internal.permissions import (
    HasProjectPermission,
    HasWeniProjectPermission,
    PermissionsLevels,
)
from retail.projects.models import Project
from retail.services.connect.service import ConnectService

User = get_user_model()


class HasProjectPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )

        content_type = ContentType.objects.get_for_model(User)
        self.internal_permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="can communicate internally",
            content_type=content_type,
        )

        self.mock_connect_service = Mock(spec=ConnectService)
        self.permission = HasProjectPermission(
            connect_service=self.mock_connect_service
        )

    def _make_drf_request(self, django_request, user=None):
        """Convert Django request to DRF request with authentication"""
        if user:
            force_authenticate(django_request, user=user)
        return Request(django_request)

    def test_missing_project_uuid_returns_false(self):
        """Test that missing Project-Uuid header returns False"""
        django_request = self.factory.get("/")
        request = self._make_drf_request(django_request, user=self.user)

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_unauthenticated_user_returns_false(self):
        """Test that unauthenticated user returns False"""
        django_request = self.factory.get("/", HTTP_PROJECT_UUID="test-uuid")
        django_request.user = Mock()
        django_request.user.is_authenticated = False
        request = self._make_drf_request(django_request)

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_internal_user_missing_user_email_returns_false(self):
        """Test that internal user without user_email param returns False"""
        self.user.user_permissions.add(self.internal_permission)

        django_request = self.factory.get("/", HTTP_PROJECT_UUID="test-uuid")
        request = self._make_drf_request(django_request, user=self.user)

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_internal_user_with_user_email_success(self):
        """Test successful internal user permission check"""
        self.user.user_permissions.add(self.internal_permission)

        django_request = self.factory.get(
            "/?user_email=other@example.com", HTTP_PROJECT_UUID="test-uuid"
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        result = self.permission.has_permission(request, None)

        self.assertTrue(result)
        self.mock_connect_service.get_user_permissions.assert_called_once_with(
            "test-uuid", "other@example.com"
        )

    def test_internal_user_non_200_status_returns_false(self):
        """Test that non-200 status from connect service returns False"""
        self.user.user_permissions.add(self.internal_permission)

        django_request = self.factory.get(
            "/?user_email=other@example.com", HTTP_PROJECT_UUID="test-uuid"
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            404,
            {"error": "Not found"},
        )

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_internal_user_insufficient_permissions_returns_false(self):
        """Test that insufficient project authorization returns False"""
        self.user.user_permissions.add(self.internal_permission)

        django_request = self.factory.get(
            "/?user_email=other@example.com", HTTP_PROJECT_UUID="test-uuid"
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 1},
        )

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_regular_user_missing_auth_header_returns_false(self):
        """Test that regular user without Authorization header returns False"""
        django_request = self.factory.get("/", HTTP_PROJECT_UUID="test-uuid")
        request = self._make_drf_request(django_request, user=self.user)

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_regular_user_invalid_auth_header_returns_false(self):
        """Test that regular user with invalid Authorization header returns False"""
        django_request = self.factory.get(
            "/", HTTP_PROJECT_UUID="test-uuid", HTTP_AUTHORIZATION="Invalid token"
        )
        request = self._make_drf_request(django_request, user=self.user)

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_regular_user_with_valid_token_success(self):
        """Test successful regular user permission check"""
        django_request = self.factory.get(
            "/",
            HTTP_PROJECT_UUID="test-uuid",
            HTTP_AUTHORIZATION="Bearer valid-jwt-token",
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        result = self.permission.has_permission(request, None)

        self.assertTrue(result)
        self.mock_connect_service.get_user_permissions.assert_called_once_with(
            "test-uuid", "test@example.com", "valid-jwt-token"
        )

    def test_regular_user_non_200_status_returns_false(self):
        """Test that regular user with non-200 status returns False"""
        django_request = self.factory.get(
            "/",
            HTTP_PROJECT_UUID="test-uuid",
            HTTP_AUTHORIZATION="Bearer valid-jwt-token",
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            403,
            {"error": "Forbidden"},
        )

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_regular_user_insufficient_permissions_returns_false(self):
        """Test that regular user with insufficient permissions returns False"""
        django_request = self.factory.get(
            "/",
            HTTP_PROJECT_UUID="test-uuid",
            HTTP_AUTHORIZATION="Bearer valid-jwt-token",
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 4},
        )

        result = self.permission.has_permission(request, None)

        self.assertFalse(result)

    def test_contributor_permission_allowed(self):
        """Test that contributor level permission is allowed"""
        self.user.user_permissions.add(self.internal_permission)

        django_request = self.factory.get(
            "/?user_email=other@example.com", HTTP_PROJECT_UUID="test-uuid"
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        result = self.permission.has_permission(request, None)

        self.assertTrue(result)

    def test_moderator_permission_allowed(self):
        """Test that moderator level permission is allowed"""
        self.user.user_permissions.add(self.internal_permission)

        django_request = self.factory.get(
            "/?user_email=other@example.com", HTTP_PROJECT_UUID="test-uuid"
        )
        request = self._make_drf_request(django_request, user=self.user)

        self.mock_connect_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        result = self.permission.has_permission(request, None)

        self.assertTrue(result)

    def test_default_connect_service_initialization(self):
        """Test that HasProjectPermission initializes with default ConnectService when none provided"""
        permission = HasProjectPermission()

        self.assertIsNotNone(permission.connect_service)

    def test_custom_connect_service_initialization(self):
        """Test that HasProjectPermission uses provided ConnectService"""
        custom_service = Mock(spec=ConnectService)
        permission = HasProjectPermission(connect_service=custom_service)

        self.assertEqual(permission.connect_service, custom_service)


class HasWeniProjectPermissionTest(TestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.connect_service = Mock(spec=ConnectService)
        self.permission = HasWeniProjectPermission(connect_service=self.connect_service)

    def _request_with_auth(self, auth):
        request = Request(self.factory.post("/"))
        request.auth = auth
        return request

    def _grant(self, level=PermissionsLevels.contributor):
        self.connect_service.get_user_permissions.return_value = (
            200,
            {"project_authorization": level},
        )

    def test_non_weni_context_returns_false(self):
        request = self._request_with_auth(None)

        self.assertFalse(self.permission.has_permission(request, None))

    def test_internal_caller_bypasses_check(self):
        auth = WeniAuthContext(vtex_account="mystore", is_internal=True)
        request = self._request_with_auth(auth)

        self.assertTrue(self.permission.has_permission(request, None))
        self.connect_service.get_user_permissions.assert_not_called()

    def test_missing_user_email_returns_false(self):
        auth = WeniAuthContext(vtex_account="mystore", user_email=None)
        request = self._request_with_auth(auth)

        self.assertFalse(self.permission.has_permission(request, None))

    def test_resolves_project_from_vtex_account(self):
        project = Project.objects.create(
            name="Test", uuid=uuid4(), vtex_account="mystore"
        )
        auth = WeniAuthContext(vtex_account="mystore", user_email="user@weni.ai")
        request = self._request_with_auth(auth)
        self._grant()

        self.assertTrue(self.permission.has_permission(request, None))
        self.connect_service.get_user_permissions.assert_called_once_with(
            str(project.uuid), "user@weni.ai"
        )

    def test_prefers_project_uuid_claim(self):
        project_uuid = str(uuid4())
        auth = WeniAuthContext(project_uuid=project_uuid, user_email="user@weni.ai")
        request = self._request_with_auth(auth)
        self._grant(level=PermissionsLevels.moderator)

        self.assertTrue(self.permission.has_permission(request, None))
        self.connect_service.get_user_permissions.assert_called_once_with(
            project_uuid, "user@weni.ai"
        )

    def test_unknown_vtex_account_returns_false(self):
        auth = WeniAuthContext(vtex_account="ghost", user_email="user@weni.ai")
        request = self._request_with_auth(auth)

        self.assertFalse(self.permission.has_permission(request, None))
        self.connect_service.get_user_permissions.assert_not_called()

    def test_non_200_status_returns_false(self):
        Project.objects.create(name="Test", uuid=uuid4(), vtex_account="mystore")
        auth = WeniAuthContext(vtex_account="mystore", user_email="user@weni.ai")
        request = self._request_with_auth(auth)
        self.connect_service.get_user_permissions.return_value = (
            403,
            {"error": "Forbidden"},
        )

        self.assertFalse(self.permission.has_permission(request, None))

    def test_insufficient_level_returns_false(self):
        Project.objects.create(name="Test", uuid=uuid4(), vtex_account="mystore")
        auth = WeniAuthContext(vtex_account="mystore", user_email="user@weni.ai")
        request = self._request_with_auth(auth)
        self._grant(level=PermissionsLevels.viewer)

        self.assertFalse(self.permission.has_permission(request, None))

    def test_default_connect_service_initialization(self):
        permission = HasWeniProjectPermission()

        self.assertIsNotNone(permission.connect_service)
