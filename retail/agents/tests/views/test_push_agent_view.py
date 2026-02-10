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
            source_type="LIBRARY",
            metadata={
                "type": "status",
                "tags": ["approved", "final"],
            },
            config={},
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
        )

    @patch("retail.agents.domains.agent_management.views.validate_agent_rules.delay")
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_success(self, mock_push_agent_usecase, mock_validate_task):
        """Test successful agent push with authenticated user"""
        mock_agent = self._create_mock_agent_response()
        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        response = self._make_push_request()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])

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

    @patch("retail.agents.domains.agent_management.views.validate_agent_rules.delay")
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_internal_user_success(
        self, mock_push_agent_usecase, mock_validate_task
    ):
        """Test agent push by internal user querying another user"""
        mock_agent = self._create_mock_agent_response()
        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        response = self._make_push_request(user_email="other@example.com")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])

    def test_push_agent_invalid_json(self):
        """Test that invalid JSON in agents field returns validation error"""
        data = {
            "project_uuid": str(self.project.uuid),
            "agents": "invalid json",
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url, data=data, files=files, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("agents", response.json())

    def test_push_agent_missing_agents_field(self):
        """Test that missing agents field returns validation error"""
        data = {
            "project_uuid": str(self.project.uuid),
        }

        response = self.client.post(self.url, data=data, format="multipart")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("retail.agents.domains.agent_management.views.validate_agent_rules.delay")
    @patch("retail.agents.domains.agent_management.views.PushAgentUseCase")
    def test_push_agent_with_credentials(
        self, mock_push_agent_usecase, mock_validate_task
    ):
        """Test agent push with credentials parsing"""
        agent_data_with_credentials = {
            "agents": {
                "agent1": {
                    **self.agent_data["agents"]["agent1"],
                    "credentials": {
                        "api_key": {
                            "credentials": ["key1", "key2"],
                            "label": "API Key",
                            "placeholder": "Enter your API key",
                            "is_confidential": True,
                        }
                    },
                }
            }
        }

        mock_agent = self._create_mock_agent_response()
        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(agent_data_with_credentials),
        }
        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url, data=data, files=files, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        mock_push_agent_instance.execute.assert_called_once()

        call_args = mock_push_agent_instance.execute.call_args
        payload = call_args[1]["payload"]
        agent = payload["agents"]["agent1"]

        self.assertEqual(len(agent["credentials"]), 1)
        self.assertEqual(agent["credentials"][0]["key"], "api_key")
        self.assertEqual(agent["credentials"][0]["label"], "API Key")
        self.assertTrue(agent["credentials"][0]["is_confidential"])
