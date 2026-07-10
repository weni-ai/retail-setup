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


@with_test_settings
class PaymentRecoveryHookConfigViewTest(BaseTestMixin, APITestCase):
    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(name="Project 1", uuid=uuid4())
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Payment Recovery",
            slug="payment-recovery",
            description="PIX recovery",
            project=self.project,
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            config={
                "payment_recovery": {
                    "hook_created": True,
                    "sales_channels": ["1"],
                }
            },
        )
        self.url = reverse(
            "payment-recovery-hook-config",
            args=[str(self.integrated_agent.uuid)],
        )
        self.user = User.objects.create_user(
            username="testuser", password="12345", email="test@example.com"
        )
        self.client.force_authenticate(self.user)

    def _request_headers(self):
        return {"HTTP_PROJECT_UUID": str(self.project.uuid)}

    @patch(
        "retail.agents.domains.agent_integration.views.PaymentRecoveryHookConfigUseCase"
    )
    def test_get_returns_hook_config(self, mock_use_case_cls):
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent
        mock_use_case.get_hook_config.return_value = {
            "sales_channels": ["1"],
            "hook_created": True,
        }
        mock_use_case_cls.return_value = mock_use_case

        response = self.client.get(
            self.url,
            **self._request_headers(),
            QUERY_STRING="user_email=test@example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.json(),
            {"sales_channels": ["1"], "hook_created": True},
        )

    @patch(
        "retail.agents.domains.agent_integration.views.PaymentRecoveryHookConfigUseCase"
    )
    def test_patch_updates_sales_channels(self, mock_use_case_cls):
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent
        mock_use_case.update_sales_channels.return_value = {
            "sales_channels": ["2"],
            "hook_created": True,
        }
        mock_use_case_cls.return_value = mock_use_case

        response = self.client.patch(
            self.url,
            data={"sales_channels": ["2"]},
            format="json",
            **self._request_headers(),
            QUERY_STRING="user_email=test@example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.update_sales_channels.assert_called_once_with(
            self.integrated_agent,
            ["2"],
        )
        self.assertEqual(
            response.json(),
            {"sales_channels": ["2"], "hook_created": True},
        )

    def test_patch_requires_sales_channels_field(self):
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        response = self.client.patch(
            self.url,
            data={},
            format="json",
            **self._request_headers(),
            QUERY_STRING="user_email=test@example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("sales_channels", response.json())
