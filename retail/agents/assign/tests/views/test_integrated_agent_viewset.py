from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from uuid import uuid4

from retail.agents.assign.models import IntegratedAgent
from retail.agents.push.models import Agent
from retail.projects.models import Project

User = get_user_model()


class IntegratedAgentViewSetTest(APITestCase):
    def setUp(self):
        self.project1 = Project.objects.create(name="Project 1", uuid=uuid4())
        self.project2 = Project.objects.create(name="Project 2", uuid=uuid4())

        # Create Agent instances first since IntegratedAgent requires an agent
        self.agent1 = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent 1",
            slug="test-agent-1",
            description="Test agent description",
            project=self.project1,
        )
        self.agent2 = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent 2",
            slug="test-agent-2",
            description="Test agent description",
            project=self.project1,
        )
        self.agent3 = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent 3",
            slug="test-agent-3",
            description="Test agent description",
            project=self.project2,
        )

        self.integrated_agent1 = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent1,
            project=self.project1,
        )
        self.integrated_agent2 = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent2,
            project=self.project1,
        )
        self.integrated_agent3 = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent3,
            project=self.project2,
        )

        self.user = User.objects.create_user(username="testuser", password="12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.list_url = reverse("assigned-agents-list")
        self.detail_url1 = reverse(
            "assigned-agents-detail", args=[str(self.integrated_agent1.uuid)]
        )
        self.detail_url2 = reverse(
            "assigned-agents-detail", args=[str(self.integrated_agent2.uuid)]
        )
        self.detail_url3 = reverse(
            "assigned-agents-detail", args=[str(self.integrated_agent3.uuid)]
        )

    @patch("retail.agents.assign.views.ListIntegratedAgentUseCase")
    def test_list_integrated_agents_with_valid_project_uuid(self, mock_use_case_class):
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = [
            self.integrated_agent1,
            self.integrated_agent2,
        ]
        mock_use_case_class.return_value = mock_use_case

        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once_with(str(self.project1.uuid))

        returned_uuids = {agent["uuid"] for agent in response.json()}
        self.assertIn(str(self.integrated_agent1.uuid), returned_uuids)
        self.assertIn(str(self.integrated_agent2.uuid), returned_uuids)

    def test_list_integrated_agents_missing_project_uuid_header(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    @patch("retail.agents.assign.views.RetrieveIntegratedAgentUseCase")
    def test_retrieve_integrated_agent_with_permission(self, mock_use_case_class):
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = self.integrated_agent1
        mock_use_case_class.return_value = mock_use_case

        response = self.client.get(
            self.detail_url1, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["uuid"], str(self.integrated_agent1.uuid))
        mock_use_case.execute.assert_called_once_with(str(self.integrated_agent1.uuid))

    @patch("retail.agents.assign.views.RetrieveIntegratedAgentUseCase")
    def test_retrieve_integrated_agent_without_permission(self, mock_use_case_class):
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = self.integrated_agent3
        mock_use_case_class.return_value = mock_use_case

        response = self.client.get(
            self.detail_url3, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_integrated_agent_missing_project_uuid_header(self):
        response = self.client.get(self.detail_url1)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    @patch("retail.agents.assign.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_integrated_agent_success(self, mock_use_case_class):
        mock_use_case = MagicMock()
        updated_agent = self.integrated_agent1
        mock_use_case.execute.return_value = updated_agent
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self.client.patch(
            self.detail_url1,
            data=update_data,
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once()

    def test_partial_update_integrated_agent_missing_project_uuid_header(self):
        update_data = {"contact_percentage": 20}

        response = self.client.patch(self.detail_url1, data=update_data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    def test_unauthenticated_access(self):
        self.client.logout()

        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )  # AllowAny permission

        response = self.client.get(
            self.detail_url1, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(
            response.status_code, status.HTTP_200_OK
        )  # AllowAny permission
