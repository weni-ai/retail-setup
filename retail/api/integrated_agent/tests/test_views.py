from uuid import uuid4
from unittest.mock import patch

from rest_framework.test import APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from retail.agents.domains.agent_management.models import Agent
from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.projects.models import Project
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)

User = get_user_model()


@with_test_settings
class SendTestTemplateViewTest(BaseTestMixin, APITestCase):
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
        self.setup_internal_user_permissions(self.user)
        self.client.force_authenticate(user=self.user)

        self.base_headers = {"Project-Uuid": str(self.project.uuid)}
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
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )
        mock_use_case = mock_use_case_class.return_value

        response = self.client.post(
            f"{self._get_url()}?user_email={self.user.email}",
            data=self.valid_payload,
            format="json",
            headers=self.base_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_use_case.execute.assert_called_once()

    @patch("retail.api.integrated_agent.views.SendTestTemplateUseCase")
    def test_send_test_template_without_variables(self, mock_use_case_class):
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )
        mock_use_case = mock_use_case_class.return_value

        payload = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "abandoned_cart",
        }

        response = self.client.post(
            f"{self._get_url()}?user_email={self.user.email}",
            data=payload,
            format="json",
            headers=self.base_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_use_case.execute.assert_called_once()

    def test_send_test_template_invalid_agent(self):
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        payload = {
            "contact_urns": ["whatsapp:5584999999999"],
            "agent": "invalid_agent",
        }

        response = self.client.post(
            f"{self._get_url()}?user_email={self.user.email}",
            data=payload,
            format="json",
            headers=self.base_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_test_template_empty_contact_urns(self):
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        payload = {
            "contact_urns": [],
            "agent": "abandoned_cart",
        }

        response = self.client.post(
            f"{self._get_url()}?user_email={self.user.email}",
            data=payload,
            format="json",
            headers=self.base_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_test_template_missing_required_fields(self):
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        response = self.client.post(
            f"{self._get_url()}?user_email={self.user.email}",
            data={},
            format="json",
            headers=self.base_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_send_test_template_unauthenticated(self):
        self.client.force_authenticate(user=None)

        response = self.client.post(
            self._get_url(),
            data=self.valid_payload,
            format="json",
            headers=self.base_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_send_test_template_missing_project_uuid_header(self):
        response = self.client.post(
            f"{self._get_url()}?user_email={self.user.email}",
            data=self.valid_payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_send_test_template_insufficient_permissions(self):
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        response = self.client.post(
            f"{self._get_url()}?user_email={self.user.email}",
            data=self.valid_payload,
            format="json",
            headers=self.base_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
