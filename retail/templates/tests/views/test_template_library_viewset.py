from unittest.mock import patch, MagicMock

from uuid import uuid4

from django.urls import reverse
from django.contrib.auth.models import User, Permission
from django.contrib.contenttypes.models import ContentType
from rest_framework import status
from rest_framework.test import APITestCase

from retail.templates.models import Template, Version
from retail.agents.models import PreApprovedTemplate, Agent
from retail.projects.models import Project

CONNECT_SERVICE_PATH = "retail.internal.permissions.ConnectService"


class TestTemplateLibraryViewSet(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )

        # Authenticate the user
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Test Project",
        )

        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent",
            project=self.project,
        )

        self.parent = PreApprovedTemplate.objects.create(
            uuid=uuid4(),
            name="test_parent",
            display_name="Test Parent Template",
            start_condition="test condition",
            agent=self.agent,
        )

        self.template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )

        self.version = Version.objects.create(
            template=self.template,
            template_name="test_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )

        self.template.current_version = self.version
        self.template.save()

        self.app_uuid = str(uuid4())
        self.project_uuid = str(self.project.uuid)
        self.update_library_usecase = MagicMock()
        self.update_library_usecase_patch = patch(
            "retail.templates.views.UpdateLibraryTemplateUseCase",
            return_value=self.update_library_usecase,
        )
        self.update_library_usecase_patch.start()
        self.addCleanup(self.update_library_usecase_patch.stop)

    def _add_internal_permission_to_user(self):
        """Helper method to add can_communicate_internally permission to user"""
        content_type = ContentType.objects.get_for_model(User)
        permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="Can communicate internally",
            content_type=content_type,
        )
        self.user.user_permissions.add(permission)
        self.user.save()

    def _get_project_headers_and_params(self):
        """Helper method to get standard headers and params for HasProjectPermission"""
        return {"HTTP_PROJECT_UUID": str(self.project.uuid)}, {
            "user_email": self.user.email
        }

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_success(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.update_library_usecase.execute.return_value = self.template

        payload = {
            "library_template_button_inputs": [
                {
                    "type": "URL",
                    "url": {
                        "base_url": "https://example.com",
                        "url_suffix_example": "/path",
                    },
                }
            ]
        }

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}&user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "APPROVED")

        # Verify the use case was called with correct data
        self.update_library_usecase.execute.assert_called_once()
        call_args = self.update_library_usecase.execute.call_args[0][0]
        self.assertEqual(call_args["template_uuid"], str(self.template.uuid))
        self.assertEqual(call_args["app_uuid"], self.app_uuid)
        self.assertEqual(call_args["project_uuid"], self.project_uuid)
        self.assertEqual(
            call_args["library_template_button_inputs"],
            payload["library_template_button_inputs"],
        )

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_missing_app_uuid(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?project_uuid={self.project_uuid}&user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("app_uuid and project_uuid are required", str(response.data))
        self.update_library_usecase.execute.assert_not_called()

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_missing_project_uuid(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("app_uuid and project_uuid are required", str(response.data))
        self.update_library_usecase.execute.assert_not_called()

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_missing_both_query_params(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("app_uuid and project_uuid are required", str(response.data))
        self.update_library_usecase.execute.assert_not_called()

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_empty_payload(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.update_library_usecase.execute.return_value = self.template

        payload = {}

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}&user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_invalid_serializer_data(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        payload = {"library_template_button_inputs": "invalid_data"}

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}&user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.update_library_usecase.execute.assert_not_called()

    # ===== PERMISSION TESTS =====

    def test_missing_project_uuid_header_returns_403(self):
        """Test that missing Project-Uuid header returns 403 for HasProjectPermission"""
        self._add_internal_permission_to_user()

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}&user_email={self.user.email}"

        # Missing Project-Uuid header
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    def test_missing_user_email_query_param_returns_403(self, mock_connect_service):
        """Test that missing user_email query param returns 403 for internal users"""
        self._add_internal_permission_to_user()

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}"

        # Missing user_email query param
        response = self.client.patch(
            url, payload, format="json", HTTP_PROJECT_UUID=str(self.project.uuid)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_connect_service.return_value.get_user_permissions.assert_not_called()

    def test_unauthenticated_user_returns_403(self):
        """Test that unauthenticated users get 403"""
        self.client.force_authenticate(None)  # Remove authentication

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}"

        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
