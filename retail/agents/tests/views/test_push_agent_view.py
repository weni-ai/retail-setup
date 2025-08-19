import json

from unittest.mock import patch, MagicMock
from types import SimpleNamespace

from django.urls import reverse
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from uuid import uuid4

from retail.projects.models import Project
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)


@with_test_settings
class PushAgentViewE2ETest(BaseTestMixin, APITestCase):
    def setUp(self):
        super().setUp()

        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.user = User.objects.create_user(
            username="testuser", password="12345", email="test@example.com"
        )
        self.setup_internal_user_permissions(self.user)

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)
        self._setup_test_data()

    def _setup_test_data(self):
        self.url = reverse("push-agent")
        self.agent_name = "Test Agent"
        self.agent_data = {
            "agents": {
                "agent1": {
                    "name": self.agent_name,
                    "description": "description",
                    "language": "pt_BR",
                    "rules": {
                        "r1": {
                            "display_name": "Approved Status",
                            "template": "approved_status",
                            "start_condition": "When a status is approved",
                            "source": {
                                "entrypoint": "main.ApprovedStatus",
                                "path": "rules/approved_status",
                            },
                        }
                    },
                    "pre_processing": {},
                }
            }
        }
        self.file_content = b"print('hello world')"
        self.uploaded_file = SimpleUploadedFile("test.py", self.file_content)

    def _create_mock_agent_response(self) -> SimpleNamespace:
        """Creates a standard mock agent response"""
        mock_template = SimpleNamespace(
            uuid=uuid4(),
            name="approved_status",
            content="some content",
            display_name="display",
            start_condition="when",
            is_valid=True,
            metadata={
                "type": "status",
                "tags": ["approved", "final"],
            },
        )

        mock_templates_manager = MagicMock()
        mock_templates_manager.all.return_value = [mock_template]

        return SimpleNamespace(
            uuid=uuid4(),
            slug="test_agent",
            name=self.agent_name,
            description="description",
            language="pt_BR",
            lambda_arn="arn:aws:lambda:region:123:function:test",
            is_oficial=False,
            templates=mock_templates_manager,
            examples=[{"name": "example1", "value": "value1"}],
        )

    def _make_push_request(self, user_email: str = "test@example.com") -> dict:
        """Makes a standard push agent request"""
        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        return self.client.post(
            f"{self.url}?user_email={user_email}",
            data=data,
            files=files,
            format="multipart",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

    @patch(
        "retail.agents.domains.agent_management.views.validate_pre_approved_templates.delay"
    )
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_success(self, mock_push_agent_usecase, mock_validate_task):
        """Test successful agent push using contributor permissions"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_agent = self._create_mock_agent_response()
        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        response = self._make_push_request()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )

    def test_push_agent_unauthenticated(self):
        """Test that unauthenticated user cannot push agent"""
        self.client.force_authenticate(user=None)

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url, data=data, files=files, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_management.views.validate_pre_approved_templates.delay"
    )
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_missing_project_permission(
        self, mock_push_agent_usecase, mock_validate_task
    ):
        """Test that user without project permission cannot push agent"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        response = self._make_push_request()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_push_agent_usecase.assert_not_called()
        mock_validate_task.assert_not_called()
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )

    def test_push_agent_missing_project_uuid_header(self):
        """Test that request without Project-Uuid header is rejected"""
        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url,
            data=data,
            files=files,
            format="multipart",
            HTTP_AUTHORIZATION="Bearer valid-jwt-token",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_management.views.validate_pre_approved_templates.delay"
    )
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_connect_service_error(
        self, mock_push_agent_usecase, mock_validate_task
    ):
        """Test behavior when ConnectService returns error"""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.USER_NOT_FOUND
        )

        response = self._make_push_request()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_push_agent_usecase.assert_not_called()
        mock_validate_task.assert_not_called()
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )

    @patch(
        "retail.agents.domains.agent_management.views.validate_pre_approved_templates.delay"
    )
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_internal_user_success(
        self, mock_push_agent_usecase, mock_validate_task
    ):
        """Test agent push by internal user querying another user"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_agent = self._create_mock_agent_response()
        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        response = self._make_push_request(user_email="other@example.com")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "other@example.com"
        )

    @patch(
        "retail.agents.domains.agent_management.views.validate_pre_approved_templates.delay"
    )
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_moderator_permission_success(
        self, mock_push_agent_usecase, mock_validate_task
    ):
        """Test agent push with moderator permissions"""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.success_scenario(permission_level=3)
        )

        mock_agent = self._create_mock_agent_response()
        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        response = self._make_push_request()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )

    @patch(
        "retail.agents.domains.agent_management.views.validate_pre_approved_templates.delay"
    )
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_server_error_scenario(
        self, mock_push_agent_usecase, mock_validate_task
    ):
        """Test behavior when ConnectService has internal error"""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.INTERNAL_ERROR
        )

        response = self._make_push_request()

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_push_agent_usecase.assert_not_called()
        mock_validate_task.assert_not_called()
