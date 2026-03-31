from uuid import uuid4
from unittest.mock import patch

from rest_framework.test import APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project

User = get_user_model()


class SendTestTemplateViewTest(APITestCase):
    def setUp(self):
        super().setUp()

        self.project = Project.objects.create(name="Test Project", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            is_oficial=True,
            name="Abandoned Cart Agent",
            slug="abandoned_cart",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
        )

        self.user = User.objects.create_user(
            username="testuser", password="12345", email="testuser@example.com"
        )
        self.client.force_authenticate(user=self.user)

        self.valid_payload = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "abandoned_cart",
            "variables": ["var1", "var2"],
        }

    def _get_url(self, integrated_agent_uuid=None):
        uuid = integrated_agent_uuid or self.integrated_agent.uuid
        return reverse(
            "send-test-template",
            kwargs={"integrated_agent_uuid": uuid},
        )

    @patch("retail.api.integrated_agent.views.SendTestTemplateUseCase")
    def test_send_test_template_success(self, mock_use_case_class):
        mock_use_case = mock_use_case_class.return_value

        response = self.client.post(
            self._get_url(),
            data=self.valid_payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_use_case.execute.assert_called_once()

    @patch("retail.api.integrated_agent.views.SendTestTemplateUseCase")
    def test_send_test_template_without_variables(self, mock_use_case_class):
        mock_use_case = mock_use_case_class.return_value

        payload = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "abandoned_cart",
        }

        response = self.client.post(
            self._get_url(),
            data=payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_use_case.execute.assert_called_once()

    def test_send_test_template_invalid_agent(self):
        payload = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "invalid_agent",
        }

        response = self.client.post(
            self._get_url(),
            data=payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_test_template_empty_contact_urns(self):
        payload = {
            "contact_urns": [],
            "agent": "abandoned_cart",
        }

        response = self.client.post(
            self._get_url(),
            data=payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_test_template_missing_required_fields(self):
        response = self.client.post(
            self._get_url(),
            data={},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_test_template_unauthenticated(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self._get_url(),
            data=self.valid_payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
