from uuid import uuid4
from unittest.mock import patch

from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from retail.agents.models import Agent, IntegratedAgent
from retail.projects.models import Project

User = get_user_model()


class UnassignAgentViewTest(APITestCase):
    def setUp(self):
        # Mock the datalake audit function in the UnassignAgentUseCase
        patcher = patch(
            "retail.agents.usecases.unassign_agent.send_commerce_webhook_data"
        )
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

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
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_unassign_agent_oficial_success(self):
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        response = self.client.post(url, HTTP_PROJECT_UUID=str(self.project.uuid))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            IntegratedAgent.objects.filter(
                agent=self.agent_oficial, project=self.project, is_active=True
            ).exists()
        )

    def test_unassign_agent_not_oficial_success(self):
        url = reverse(
            "unassign-agent", kwargs={"agent_uuid": self.agent_not_oficial.uuid}
        )
        response = self.client.post(url, HTTP_PROJECT_UUID=str(self.project.uuid))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            IntegratedAgent.objects.filter(
                agent=self.agent_not_oficial, project=self.project, is_active=True
            ).exists()
        )

    def test_unassign_agent_not_oficial_wrong_project(self):
        url = reverse(
            "unassign-agent", kwargs={"agent_uuid": self.agent_not_oficial.uuid}
        )
        response = self.client.post(url, HTTP_PROJECT_UUID=str(uuid4()))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassign_agent_missing_project_uuid_header(self):
        url = reverse("unassign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        response = self.client.post(url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_unassign_agent_not_found(self):
        url = reverse("unassign-agent", kwargs={"agent_uuid": uuid4()})
        response = self.client.post(url, HTTP_PROJECT_UUID=str(self.project.uuid))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
