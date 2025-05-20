from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from uuid import uuid4
from urllib.parse import urlencode

from retail.agents.models import Agent
from retail.projects.models import Project

User = get_user_model()


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
        self.user = User.objects.create_user(username="testuser", password="12345")
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_assign_agent_oficial(self):
        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode({"app_uuid": str(uuid4())})
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("client_secret", response.data)

    def test_assign_agent_not_oficial_wrong_project(self):
        url = reverse(
            "assign-agent", kwargs={"agent_uuid": self.agent_not_oficial.uuid}
        )
        query_string = urlencode({"app_uuid": str(uuid4())})
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            HTTP_PROJECT_UUID=str(uuid4()),
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_assign_agent_not_oficial_correct_project(self):
        url = reverse(
            "assign-agent", kwargs={"agent_uuid": self.agent_not_oficial.uuid}
        )
        query_string = urlencode({"app_uuid": str(uuid4())})
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("client_secret", response.data)

    def test_missing_project_uuid_header(self):
        url = reverse("assign-agent", kwargs={"agent_uuid": self.agent_oficial.uuid})
        query_string = urlencode({"app_uuid": str(uuid4())})
        full_url = f"{url}?{query_string}"

        response = self.client.post(full_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_agent_not_found(self):
        url = reverse("assign-agent", kwargs={"agent_uuid": uuid4()})
        query_string = urlencode({"app_uuid": str(uuid4())})
        full_url = f"{url}?{query_string}"

        response = self.client.post(
            full_url,
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
