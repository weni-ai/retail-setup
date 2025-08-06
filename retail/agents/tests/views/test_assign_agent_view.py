from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from uuid import uuid4
from urllib.parse import urlencode
from unittest.mock import patch, MagicMock

from retail.agents.models import Agent
from retail.projects.models import Project

User = get_user_model()

CONNECT_SERVICE_PATH = "retail.internal.permissions.ConnectService"


class AssignAgentViewTest(APITestCase):
    def setUp(self):
        self.project = Project.objects.create(name="Project", uuid=uuid4())
        self.agent_oficial = Agent.objects.create(
            uuid=uuid4(),
            name="Agent 1",
            is_oficial=True,
            lambda_arn="arn:aws:lambda:...",
            project=self.project,
        )
        self.agent_not_oficial = Agent.objects.create(
            uuid=uuid4(),
            name="Agent 2",
            is_oficial=False,
            lambda_arn="arn:aws:lambda:...",
            project=self.project,
        )
        self.user = User.objects.create_user(
            username="testuser", password="12345", email="testuser@example.com"
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_assign_agent_oficial(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_assign_agent_not_oficial_correct_project(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse(
            "assign-agent", kwargs={"agent_uuid": self.agent_not_oficial.uuid}
        )
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_assign_agent_permission_denied_by_service(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 1},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_assign_agent_missing_user_email(self, mock_integrations_service_class):
        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_project_uuid_header(self):
        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(full_url)

        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN],
        )

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_agent_not_found(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse("assign-agent", kwargs={"agent_uuid": uuid4()})
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_assign_agent_permission_denied_by_service_error(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            500,
            {"error": "Service unavailable"},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_assign_agent_not_oficial_from_another_project(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        another_project = Project.objects.create(name="Another Project", uuid=uuid4())
        agent_from_another_project = Agent.objects.create(
            uuid=uuid4(),
            name="Agent from another project",
            is_oficial=False,
            lambda_arn="arn:aws:lambda:...",
            project=another_project,
        )

        url = reverse(
            "assign-agent", kwargs={"agent_uuid": agent_from_another_project.uuid}
        )
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_missing_app_uuid_param(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {"channel_uuid": str(uuid4()), "user_email": self.user.email}
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.usecases.assign_agent.IntegrationsService")
    def test_missing_channel_uuid_param(
        self, mock_integrations_service_class, mock_connect_service
    ):
        mock_connect_instance = mock_connect_service.return_value
        mock_connect_instance.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        mock_integrations_service_class.return_value = mock_integrations_service

        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {"app_uuid": str(uuid4()), "user_email": self.user.email}
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unauthenticated_user_cannot_assign_agent(self):
        self.client.force_authenticate(user=None)
        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode(
            {
                "app_uuid": str(uuid4()),
                "channel_uuid": str(uuid4()),
                "user_email": self.user.email,
            }
        )
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            headers={"Project-Uuid": str(self.project.uuid)},
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
