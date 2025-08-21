from unittest.mock import patch, MagicMock

from uuid import uuid4

from django.urls import reverse
from django.contrib.auth.models import User
from rest_framework import status
from rest_framework.test import APITestCase

from retail.templates.models import Template, Version
from retail.agents.domains.agent_management.models import PreApprovedTemplate, Agent
from retail.projects.models import Project
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)


@with_test_settings
class TestTemplateLibraryViewSet(BaseTestMixin, APITestCase):
    """
    Tests for the Template Library ViewSet.

    Tests the template library operations, including:
    - Updating library template configurations
    - Handling button inputs and URL configurations
    - Validating query parameters and request data
    - Authentication and authorization validation
    - Project-based permissions and access control
    - Error handling for missing or invalid data
    """

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_user(
            username="testuser", password="testpass123", email="test@example.com"
        )

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

        self._setup_test_data()
        self._setup_use_cases()

    def _setup_test_data(self):
        """Configure test data and variables"""
        self.app_uuid = str(uuid4())
        self.project_uuid = str(self.project.uuid)

    def _setup_use_cases(self):
        """Configure use case mocks and patches"""
        self.update_library_usecase = MagicMock()
        self.update_library_usecase_patch = patch(
            "retail.templates.views.UpdateLibraryTemplateUseCase",
            return_value=self.update_library_usecase,
        )
        self.update_library_usecase_patch.start()
        self.addCleanup(self.update_library_usecase_patch.stop)

    def _get_project_headers_and_params(self):
        """Helper method to get standard headers and params for HasProjectPermission"""
        return {"HTTP_PROJECT_UUID": str(self.project.uuid)}, {
            "user_email": self.user.email
        }

    def test_partial_update_success(self):
        """Test successful partial update of template library with valid data"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
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

        self.update_library_usecase.execute.assert_called_once()
        call_args = self.update_library_usecase.execute.call_args[0][0]
        self.assertEqual(call_args["template_uuid"], str(self.template.uuid))
        self.assertEqual(call_args["app_uuid"], self.app_uuid)
        self.assertEqual(call_args["project_uuid"], self.project_uuid)
        self.assertEqual(
            call_args["library_template_button_inputs"],
            payload["library_template_button_inputs"],
        )

    def test_partial_update_missing_app_uuid(self):
        """Test partial update fails when app_uuid query parameter is missing"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
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

    def test_partial_update_missing_project_uuid(self):
        """Test partial update fails when project_uuid query parameter is missing"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
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

    def test_partial_update_missing_both_query_params(self):
        """Test partial update fails when both app_uuid and project_uuid parameters are missing"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
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

    def test_partial_update_empty_payload(self):
        """Test partial update fails with empty payload data"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        self.update_library_usecase.execute.return_value = self.template

        payload = {}

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}&user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_invalid_serializer_data(self):
        """Test partial update fails with invalid serializer data"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        payload = {"library_template_button_inputs": "invalid_data"}

        headers, params = self._get_project_headers_and_params()
        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}&user_email={params['user_email']}"

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.update_library_usecase.execute.assert_not_called()

    def test_missing_project_uuid_header_returns_403(self):
        """Test that missing Project-UUID header returns 403 Forbidden"""
        self.setup_internal_user_permissions(self.user)

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}&user_email={self.user.email}"

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_user_email_query_param_returns_403(self):
        """Test that missing user_email query parameter returns 403 Forbidden"""
        self.setup_internal_user_permissions(self.user)

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}"

        response = self.client.patch(
            url, payload, format="json", HTTP_PROJECT_UUID=str(self.project.uuid)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_returns_403(self):
        """Test that unauthenticated users get 403 Forbidden"""
        self.client.force_authenticate(None)

        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}"

        response = self.client.patch(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
