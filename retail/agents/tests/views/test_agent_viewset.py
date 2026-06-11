from django.urls import reverse
from django.contrib.auth.models import User

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from uuid import uuid4

from retail.projects.models import Project
from retail.agents.domains.agent_management.models import Agent
from retail.internal.test_mixins import BaseTestMixin, with_test_settings


@with_test_settings
class AgentViewSetE2ETest(BaseTestMixin, APITestCase):
    """
    End-to-end tests for the Agent ViewSet.

    Tests the complete CRUD operations for agents, including:
    - Listing agents filtered by project
    - Retrieving individual agent details
    - Authentication and authorization validation
    - Project-based permissions and access control
    - Header validation for project UUID requirements
    """

    def setUp(self):
        super().setUp()

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

        self._setup_test_urls()

    def _setup_test_urls(self):
        """Configure common test URLs"""
        self.list_url = reverse("agents-list")
        self.detail_url1 = reverse("agents-detail", args=[str(self.agent1.uuid)])
        self.detail_url2 = reverse("agents-detail", args=[str(self.agent2.uuid)])
        self.detail_url3 = reverse("agents-detail", args=[str(self.agent3.uuid)])

    def test_list_agents_with_valid_project_uuid(self):
        """Test listing agents with valid project UUID returns filtered results"""
        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        returned_uuids = {agent["uuid"] for agent in response.json()}

        self.assertIn(str(self.agent1.uuid), returned_uuids)
        self.assertIn(str(self.agent2.uuid), returned_uuids)
        self.assertNotIn(str(self.agent3.uuid), returned_uuids)

    def test_list_agents_missing_project_uuid_header(self):
        """Test listing agents fails when Project-UUID header is missing"""
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    def test_retrieve_agent_with_permission(self):
        """Test retrieving agent with proper project permissions"""
        response = self.client.get(
            self.detail_url2, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["uuid"], str(self.agent2.uuid))

    def test_retrieve_agent_without_permission(self):
        """Test retrieving agent fails without proper project permissions"""
        response = self.client.get(
            self.detail_url3, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_agent_missing_project_uuid_header(self):
        """Test retrieving agent fails when Project-UUID header is missing"""
        response = self.client.get(self.detail_url1)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_access(self):
        """Test that unauthenticated users cannot access agents"""
        self.client.logout()
        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.get(
            self.detail_url1, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
