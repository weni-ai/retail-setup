from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)
from retail.projects.models import Project

User = get_user_model()

VALID_PAYLOAD = {
    "is_active": True,
    "periods": {
        "weekdays": {"from": "08:00", "to": "20:00"},
        "saturdays": {"from": "10:00", "to": "12:00"},
    },
}


@with_test_settings
class MessageTimeRestrictionViewTest(BaseTestMixin, APITestCase):
    """JWT operator path used by the IO frontend (user + project on the token)."""

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(name="Project 1", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Abandoned cart",
            slug="abandoned-cart",
            description="Abandoned cart",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            config={},
        )
        self.url = reverse(
            "abandoned-cart-message-time-restriction",
            args=[str(self.integrated_agent.uuid)],
        )
        self.user = User.objects.create_user(
            username="testuser", password="12345", email="test@example.com"
        )
        self.start_retail_auth(
            project_uuid=self.project.uuid,
            user_email=self.user.email,
            token_type="jwt",
            is_internal=False,
        )
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

    @patch(
        "retail.agents.domains.agent_integration.views.MessageTimeRestrictionUseCase"
    )
    def test_get_returns_restriction(self, mock_use_case_cls):
        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent
        mock_use_case.get_restriction.return_value = VALID_PAYLOAD
        mock_use_case_cls.return_value = mock_use_case

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), VALID_PAYLOAD)

    @patch(
        "retail.agents.domains.agent_integration.views.MessageTimeRestrictionUseCase"
    )
    def test_get_returns_inactive_when_unset(self, mock_use_case_cls):
        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent
        mock_use_case.get_restriction.return_value = {
            "is_active": False,
            "periods": None,
        }
        mock_use_case_cls.return_value = mock_use_case

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json(), {"is_active": False, "periods": None})

    def test_get_returns_404_when_agent_missing(self):
        missing_url = reverse(
            "abandoned-cart-message-time-restriction",
            args=[str(uuid4())],
        )

        response = self.client.get(missing_url)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_rejects_unauthenticated_request(self):
        self.set_retail_auth(authenticated=False)

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_rejects_viewer_role(self):
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_integration.views.MessageTimeRestrictionUseCase"
    )
    def test_put_upserts_restriction(self, mock_use_case_cls):
        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent
        mock_use_case.upsert_restriction.return_value = VALID_PAYLOAD
        mock_use_case_cls.return_value = mock_use_case

        response = self.client.put(self.url, data=VALID_PAYLOAD, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.upsert_restriction.assert_called_once_with(
            self.integrated_agent,
            VALID_PAYLOAD,
        )
        self.assertEqual(response.json(), VALID_PAYLOAD)

    def test_put_rejects_invalid_payload(self):
        response = self.client.put(self.url, data={"is_active": True}, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("periods", response.json())

    @patch(
        "retail.agents.domains.agent_integration.views.MessageTimeRestrictionUseCase"
    )
    def test_delete_removes_restriction(self, mock_use_case_cls):
        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent
        mock_use_case_cls.return_value = mock_use_case

        response = self.client.delete(self.url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        mock_use_case.delete_restriction.assert_called_once_with(self.integrated_agent)
