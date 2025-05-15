import json

from unittest.mock import patch, Mock

from django.urls import reverse
from django.contrib.auth.models import User, Permission, ContentType
from django.core.files.uploadedfile import SimpleUploadedFile

from rest_framework import status
from rest_framework.test import APITestCase, APIClient

from uuid import uuid4

from retail.projects.models import Project
from retail.agents.models import Agent


class PushAgentViewE2ETest(APITestCase):
    def setUp(self):
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")

        content_type = ContentType.objects.get_for_model(User)
        self.permission = Permission.objects.create(
            codename="can_communicate_internally",
            name="Can Communicate Internally",
            content_type=content_type,
        )
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.user.user_permissions.add(self.permission)
        self.user.save()
        self.url = reverse("push-agent")
        self.agent_name = "Test Agent"
        self.agent_data = {
            "agents": {
                "agent1": {
                    "name": self.agent_name,
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

    @patch("retail.agents.views.PushAgentUseCase")
    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    def test_push_agent_success(self, mock_validate_task, mock_push_agent_usecase):
        mock_template = Mock()
        mock_template.name = "approved_status"
        mock_template.content = "some content"
        mock_template.is_valid = True

        mock_agent = Mock(spec=Agent)
        mock_agent.uuid = uuid4()
        mock_agent.name = self.agent_name
        mock_agent.lambda_arn = "arn:aws:lambda:region:123:function:test"
        mock_agent.is_oficial = False
        mock_agent.templates = [mock_template]

        mock_push_agent_instance = mock_push_agent_usecase.return_value
        mock_push_agent_instance.execute.return_value = [mock_agent]

        self.client.force_authenticate(user=self.user)

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
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.json()[0]["name"], self.agent_name)

        mock_push_agent_instance.execute.assert_called_once()
        mock_validate_task.assert_called_once_with([str(mock_agent.uuid)])

    @patch("retail.agents.views.PushAgentUseCase")
    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    def test_push_agent_permission_denied(
        self, mock_validate_task, mock_push_agent_usecase
    ):
        user_no_perm = User.objects.create_user(username="nopermuser", password="12345")
        self.client.force_authenticate(user=user_no_perm)

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }

        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url, data=data, files=files, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        mock_push_agent_usecase.assert_not_called()
        mock_validate_task.assert_not_called()

    @patch("retail.agents.views.PushAgentUseCase")
    @patch("retail.agents.views.validate_pre_approved_templates.delay")
    def test_push_agent_unauthenticated(
        self, mock_validate_task, mock_push_agent_usecase
    ):
        self.client.force_authenticate(user=None)

        data = {
            "project_uuid": str(self.project.uuid),
            "agents": json.dumps(self.agent_data),
        }

        files = {"agent1": self.uploaded_file}

        response = self.client.post(
            self.url, data=data, files=files, format="multipart"
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        mock_push_agent_usecase.assert_not_called()
        mock_validate_task.assert_not_called()
