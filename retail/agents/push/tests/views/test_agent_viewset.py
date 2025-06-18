from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from uuid import uuid4

from retail.projects.models import Project
from retail.agents.push.models import Agent


class AgentViewSetE2ETest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

        self.project1 = Project.objects.create(name="Project 1", uuid=uuid4())
        self.project2 = Project.objects.create(name="Project 2", uuid=uuid4())

        self.agent1 = Agent.objects.create(
            name="Agent 1", project=self.project1, is_oficial=False
        )
        self.agent2 = Agent.objects.create(
            name="Agent 2", project=self.project1, is_oficial=True
        )
        self.agent3 = Agent.objects.create(
            name="Agent 3", project=self.project2, is_oficial=False
        )

        self.list_url = reverse("agents-list")
        self.detail_url1 = reverse("agents-detail", args=[str(self.agent1.uuid)])
        self.detail_url2 = reverse("agents-detail", args=[str(self.agent2.uuid)])
        self.detail_url3 = reverse("agents-detail", args=[str(self.agent3.uuid)])

    def test_list_agents_with_valid_project_uuid(self):
        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {agent["uuid"] for agent in response.json()}

        self.assertIn(str(self.agent1.uuid), returned_uuids)
        self.assertIn(str(self.agent2.uuid), returned_uuids)
        self.assertNotIn(str(self.agent3.uuid), returned_uuids)

    def test_list_agents_missing_project_uuid_header(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    def test_retrieve_agent_with_permission(self):
        response = self.client.get(
            self.detail_url2, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["uuid"], str(self.agent2.uuid))

    def test_retrieve_agent_without_permission(self):
        response = self.client.get(
            self.detail_url3, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_agent_missing_project_uuid_header(self):
        response = self.client.get(self.detail_url1)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    def test_unauthenticated_access(self):
        self.client.logout()
        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(
            self.detail_url1, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
