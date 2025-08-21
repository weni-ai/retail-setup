from rest_framework.test import APITestCase
from rest_framework import status

from django.urls import reverse
from django.contrib.auth import get_user_model

from uuid import uuid4
from urllib.parse import urlencode
from unittest.mock import patch, MagicMock

from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)

User = get_user_model()


@with_test_settings
class AssignAgentViewTest(BaseTestMixin, APITestCase):
    """
    Tests for the agent assignment view.

    Tests the complete flow of assigning agents to projects, including:
    - Authentication and authorization
    - Parameter validation
    - Different types of agents (official and non-official)
    - Integration with external services
    """

    def setUp(self):
        super().setUp()

        self.project = Project.objects.create(name="Test Project", uuid=uuid4())

        self.agent_oficial = Agent.objects.create(
            uuid=uuid4(),
            name="Official Agent",
            is_oficial=True,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:official-agent",
            project=self.project,
        )
        self.agent_not_oficial = Agent.objects.create(
            uuid=uuid4(),
            name="Custom Agent",
            is_oficial=False,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:custom-agent",
            project=self.project,
        )

        self.user = User.objects.create_user(
            username="testuser", password="12345", email="testuser@example.com"
        )

        self.setup_internal_user_permissions(self.user)

        self.client.force_authenticate(self.user)

        self._setup_test_data()

    def _setup_test_data(self):
        """Configure common test data"""
        self.base_query_params = {
            "app_uuid": str(uuid4()),
            "channel_uuid": str(uuid4()),
            "user_email": self.user.email,
        }
        self.base_headers = {"Project-Uuid": str(self.project.uuid)}

    def _make_assign_request(self, agent_uuid, query_params=None, headers=None):
        """
        Helper method to make agent assignment requests

        Args:
            agent_uuid: UUID of the agent to be assigned
            query_params: Custom query parameters
            headers: Custom headers

        Returns:
            Request response
        """
        url = reverse("assign-agent", kwargs={"agent_uuid": agent_uuid})

        params = query_params if query_params is not None else self.base_query_params
        request_headers = headers if headers is not None else self.base_headers

        query_string = urlencode(params)
        full_url = f"{url}?{query_string}"

        return self.client.post(full_url, headers=request_headers)

    def _setup_integrations_service_mock(self):
        """Configure IntegrationsService mock"""
        mock_integrations_service = MagicMock()
        mock_integrations_service.fetch_templates_from_user.return_value = {}
        return mock_integrations_service

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_assign_agent_oficial(self, mock_integrations_service_class):
        """Test official agent assignment with contributor permissions"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        response = self._make_assign_request(self.agent_oficial.uuid)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), self.user.email
        )

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_assign_agent_not_oficial_correct_project(
        self, mock_integrations_service_class
    ):
        """Test non-official agent assignment with moderator permissions"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.MODERATOR_PERMISSIONS,
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        response = self._make_assign_request(self.agent_not_oficial.uuid)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_assign_agent_permission_denied_by_service(
        self, mock_integrations_service_class
    ):
        """Test that user without adequate permission cannot assign agent"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        response = self._make_assign_request(self.agent_oficial.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_assign_agent_permission_denied_by_service_error(
        self, mock_integrations_service_class
    ):
        """Test behavior when ConnectService returns internal error"""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.INTERNAL_ERROR
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        response = self._make_assign_request(self.agent_oficial.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_assign_agent_not_oficial_from_another_project(
        self, mock_integrations_service_class
    ):
        """Test that it's not possible to assign agent from another project"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.MODERATOR_PERMISSIONS,
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        another_project = Project.objects.create(name="Another Project", uuid=uuid4())
        agent_from_another_project = Agent.objects.create(
            uuid=uuid4(),
            name="Agent from another project",
            is_oficial=False,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:other-agent",
            project=another_project,
        )

        response = self._make_assign_request(agent_from_another_project.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_missing_user_email(self, mock_integrations_service_class):
        """Test behavior when user_email is not provided"""
        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        query_params = {
            "app_uuid": str(uuid4()),
            "channel_uuid": str(uuid4()),
        }
        response = self._make_assign_request(
            self.agent_oficial.uuid, query_params=query_params
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_missing_app_uuid_param(self, mock_integrations_service_class):
        """Test behavior when app_uuid is not provided"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        query_params = {
            "channel_uuid": str(uuid4()),
            "user_email": self.user.email,
        }
        response = self._make_assign_request(
            self.agent_oficial.uuid, query_params=query_params
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_missing_channel_uuid_param(self, mock_integrations_service_class):
        """Test behavior when channel_uuid is not provided"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        query_params = {
            "app_uuid": str(uuid4()),
            "user_email": self.user.email,
        }
        response = self._make_assign_request(
            self.agent_oficial.uuid, query_params=query_params
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_missing_project_uuid_header(self):
        """Test behavior when Project-Uuid header is not provided"""
        response = self._make_assign_request(self.agent_oficial.uuid, headers={})

        self.assertIn(
            response.status_code,
            [status.HTTP_400_BAD_REQUEST, status.HTTP_403_FORBIDDEN],
        )

    @patch(
        "retail.agents.domains.agent_integration.usecases.assign.IntegrationsService"
    )
    def test_agent_not_found(self, mock_integrations_service_class):
        """Test behavior when agent is not found"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_integrations_service_class.return_value = (
            self._setup_integrations_service_mock()
        )

        nonexistent_uuid = uuid4()
        response = self._make_assign_request(nonexistent_uuid)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthenticated_user_cannot_assign_agent(self):
        """Test that unauthenticated user cannot assign agent"""
        self.client.force_authenticate(user=None)

        response = self._make_assign_request(self.agent_oficial.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
