import json

from unittest.mock import patch, MagicMock

from types import SimpleNamespace

from django.urls import reverse
from django.contrib.auth.models import User, Permission, ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from uuid import uuid4

from retail.projects.models import Project

CONNECT_SERVICE_PATH = "retail.internal.permissions.ConnectService"


class PushAgentViewE2ETest(APITestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")

        content_type = ContentType.objects.get_for_model(User)
        self.permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="Can Communicate Internally",
            content_type=content_type,
        )
        self.user = User.objects.create_user(
            username="testuser", password="12345", email="test@example.com"
        )
        self.user.user_permissions.add(self.permission)
        self.user.save()

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
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    @patch("retail.agents.views.PushAgentUseCase")
    @patch(CONNECT_SERVICE_PATH)
    def test_push_agent_success(
        self, mock_connect_service, mock_push_agent_usecase, mock_validate_task
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

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

        mock_agent = SimpleNamespace(
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

        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url + "?user_email=test@example.com",
            data=data,
            files=files,
            format="multipart",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )

    def test_push_agent_unauthenticated(self):
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

    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    @patch("retail.agents.views.PushAgentUseCase")
    @patch(CONNECT_SERVICE_PATH)
    def test_push_agent_missing_project_permission(
        self, mock_connect_service, mock_push_agent_usecase, mock_validate_task
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 1},
        )

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url + "?user_email=test@example.com",
            data=data,
            files=files,
            format="multipart",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_push_agent_usecase.assert_not_called()
        mock_validate_task.assert_not_called()
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )

    def test_push_agent_missing_project_uuid_header(self):
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

    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    @patch("retail.agents.views.PushAgentUseCase")
    @patch(CONNECT_SERVICE_PATH)
    def test_push_agent_connect_service_error(
        self, mock_connect_service, mock_push_agent_usecase, mock_validate_task
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            404,
            {"error": "Not found"},
        )

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url + "?user_email=test@example.com",
            data=data,
            files=files,
            format="multipart",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_push_agent_usecase.assert_not_called()
        mock_validate_task.assert_not_called()
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )

    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    @patch("retail.agents.views.PushAgentUseCase")
    @patch(CONNECT_SERVICE_PATH)
    def test_push_agent_internal_user_success(
        self, mock_connect_service, mock_push_agent_usecase, mock_validate_task
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

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

        mock_agent = SimpleNamespace(
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

        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url + "?user_email=other@example.com",
            data=data,
            files=files,
            format="multipart",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "other@example.com"
        )

    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    @patch("retail.agents.views.PushAgentUseCase")
    @patch(CONNECT_SERVICE_PATH)
    def test_push_agent_moderator_permission_success(
        self, mock_connect_service, mock_push_agent_usecase, mock_validate_task
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

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

        mock_agent = SimpleNamespace(
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

        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url + "?user_email=test@example.com",
            data=data,
            files=files,
            format="multipart",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), "test@example.com"
        )
