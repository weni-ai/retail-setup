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
class UnassignAgentViewTest(BaseTestMixin, APITestCase):
    """
    Tests for the agent unassignment view.

    Tests the complete flow of unassigning agents from projects, including:
    - Authentication and authorization
    - Different agent types (official and non-official)
    - Permission validation
    - Resource cleanup verification
    """

    def setUp(self):
        super().setUp()

        patcher = patch(
            "retail.agents.domains.agent_integration.usecases.unassign.send_commerce_webhook_data"
        )
        self.mock_audit = patcher.start()
        self.addCleanup(patcher.stop)

        self.project = Project.objects.create(name="Test Project", uuid=uuid4())

        self.agent_oficial = Agent.objects.create(
            uuid=uuid4(),
            is_oficial=True,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:official-agent",
            name="Official Agent",
            project=self.project,
        )
        self.agent_not_oficial = Agent.objects.create(
            uuid=uuid4(),
            is_oficial=False,
            lambda_arn="arn:aws:lambda:us-east-1:123456789012:function:custom-agent",
            name="Custom Agent",
            project=self.project,
        )

        self.integrated_agent_oficial = IntegratedAgent.objects.create(
            agent=self.agent_oficial, project=self.project, channel_uuid=uuid4()
        )
        self.integrated_agent_not_oficial = IntegratedAgent.objects.create(
            agent=self.agent_not_oficial, project=self.project, channel_uuid=uuid4()
        )

        self.user = User.objects.create_user(
            username="testuser", password="12345", email="testuser@example.com"
        )

        self.setup_internal_user_permissions(self.user)
        self.client.force_authenticate(user=self.user)
        self._setup_test_data()

    def _setup_test_data(self):
        """Configure common test data"""
        self.base_headers = {"Project-Uuid": str(self.project.uuid)}

    def _make_unassign_request(self, agent_uuid, user_email=None, headers=None):
        """
        Helper method to make agent unassignment requests

        Args:
            agent_uuid: UUID of the agent to unassign
            user_email: Email of the user (optional)
            headers: Custom headers (optional)

        Returns:
            Response from the request
        """
        url = reverse("unassign-agent", kwargs={"agent_uuid": agent_uuid})

        if user_email:
            full_url = f"{url}?user_email={user_email}"
        else:
            full_url = url

        request_headers = headers if headers is not None else self.base_headers

        return self.client.post(full_url, headers=request_headers)

    def _assert_agent_unassigned(self, agent, project):
        """
        Assert that an agent has been properly unassigned from a project

        Args:
            agent: The agent that should be unassigned
            project: The project from which the agent should be unassigned
        """
        self.assertFalse(
            IntegratedAgent.objects.filter(
                agent=agent, project=project, is_active=True
            ).exists()
        )

    def test_unassign_agent_oficial_success(self):
        """Test successful unassignment of official agent with contributor permissions"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        response = self._make_unassign_request(
            self.agent_oficial.uuid, user_email=self.user.email
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self._assert_agent_unassigned(self.agent_oficial, self.project)

    def test_unassign_agent_not_oficial_success(self):
        """Test successful unassignment of non-official agent with moderator permissions"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.MODERATOR_PERMISSIONS,
        )

        response = self._make_unassign_request(
            self.agent_not_oficial.uuid, user_email=self.user.email
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self._assert_agent_unassigned(self.agent_not_oficial, self.project)

    def test_unassign_agent_not_oficial_wrong_project(self):
        """Test unassignment fails when project UUID doesn't match agent's project"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.MODERATOR_PERMISSIONS,
        )

        wrong_project_headers = {"Project-Uuid": str(uuid4())}
        response = self._make_unassign_request(
            self.agent_not_oficial.uuid,
            user_email=self.user.email,
            headers=wrong_project_headers,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassign_agent_missing_project_uuid_header(self):
        """Test unassignment fails when Project-Uuid header is missing"""
        response = self._make_unassign_request(
            self.agent_oficial.uuid, user_email=self.user.email, headers={}
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassign_agent_not_found(self):
        """Test unassignment fails when agent does not exist"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        nonexistent_uuid = uuid4()
        response = self._make_unassign_request(
            nonexistent_uuid, user_email=self.user.email
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unassign_agent_permission_denied_by_service(self):
        """Test unassignment fails when user has insufficient permissions"""
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        response = self._make_unassign_request(
            self.agent_oficial.uuid, user_email=self.user.email
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassign_agent_permission_denied_by_service_error(self):
        """Test unassignment fails when ConnectService returns an error"""
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.INTERNAL_ERROR
        )

        response = self._make_unassign_request(
            self.agent_oficial.uuid, user_email=self.user.email
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unassign_agent_missing_user_email(self):
        """Test unassignment fails when user_email parameter is missing"""
        self.setup_connect_service_mock(
            status_code=403,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        response = self._make_unassign_request(self.agent_oficial.uuid)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_user_cannot_unassign_agent(self):
        """Test that unauthenticated users cannot unassign agents"""
        self.client.force_authenticate(user=None)

        response = self._make_unassign_request(
            self.agent_oficial.uuid, user_email=self.user.email
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
