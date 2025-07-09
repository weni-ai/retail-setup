from uuid import uuid4
from unittest.mock import patch

from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from retail.agents.models import Agent, IntegratedAgent
from retail.projects.models import Project

User = get_user_model()

CONNECT_SERVICE_PATH = "retail.internal.permissions.ConnectService"


class UnassignAgentViewTest(APITestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project", uuid=uuid4())
        self.agent_oficial = Agent.objects.create(
            uuid=uuid4(),
            is_oficial=True,
            lambda_arn="arn:aws:lambda:...",
            name="Agent Oficial",
            project=self.project,
        )
        self.agent_not_oficial = Agent.objects.create(
            uuid=uuid4(),
            is_oficial=False,
            lambda_arn="arn:aws:lambda:...",
            name="Agent Não Oficial",
            project=self.project,
        )
        self.integrated_agent_oficial = IntegratedAgent.objects.create(
            agent=self.agent_oficial, project=self.project, channel_uuid=uuid4()
        )
        self.integrated_agent_not_oficial = IntegratedAgent.objects.create(
            agent=self.agent_not_oficial, project=self.project, channel_uuid=uuid4()
        )
        self.user = User.objects.create_user(
            username="testuser", password="12345", email="testuser@example.com"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    @patch(CONNECT_SERVICE_PATH)
    def test_unassign_agent_oficial_success(self, mock_connect_service):
        mock_instance = mock_connect_service.return_value
        mock_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            IntegratedAgent.objects.filter(
                agent=self.agent_oficial, project=self.project, is_active=True
            ).exists()
        )

    @patch(CONNECT_SERVICE_PATH)
    def test_unassign_agent_not_oficial_success(self, mock_connect_service):
        mock_instance = mock_connect_service.return_value
        mock_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )
        url = reverse(
            "unassign-agent", kwargs={"agent_uuid": self.agent_not_oficial.uuid}
        )
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            IntegratedAgent.objects.filter(
                agent=self.agent_not_oficial, project=self.project, is_active=True
            ).exists()
        )

    @patch(CONNECT_SERVICE_PATH)
    def test_unassign_agent_not_oficial_wrong_project(self, mock_connect_service):
        mock_instance = mock_connect_service.return_value
        mock_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        url = reverse(
            "unassign-agent", kwargs={"agent_uuid": self.agent_not_oficial.uuid}
        )
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(uuid4())},
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassign_agent_missing_project_uuid_header(self):
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(full_url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    def test_unassign_agent_not_found(self, mock_connect_service):
        mock_instance = mock_connect_service.return_value
        mock_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )
        url = reverse("unassign-agent", kwargs={"agent_uuid": uuid4()})
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(CONNECT_SERVICE_PATH)
    def test_unassign_agent_permission_denied_by_service(self, mock_connect_service):
        mock_instance = mock_connect_service.return_value
        mock_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 1},
        )
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    def test_unassign_agent_permission_denied_by_service_error(
        self, mock_connect_service
    ):
        mock_instance = mock_connect_service.return_value
        mock_instance.get_user_permissions.return_value = (
            500,
            {"error": "Service unavailable"},
        )
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassign_agent_missing_user_email(self):
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})

        response = self.client.post(
            url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_unassign_agent(self):
        self.client.force_authenticate(user=None)
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        full_url = f"{url}?user_email={self.user.email}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
