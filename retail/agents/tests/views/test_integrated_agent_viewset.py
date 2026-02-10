from unittest.mock import patch, MagicMock

from rest_framework.test import APITestCase
from rest_framework import status

from datetime import datetime

from django.urls import reverse
from django.contrib.auth import get_user_model

from uuid import uuid4

from retail.agents.domains.agent_integration.models import (
    IntegratedAgent,
)
from retail.agents.domains.agent_management.models import (
    Agent,
    AgentRule,
)
from retail.projects.models import Project
from retail.templates.models import Template
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)

User = get_user_model()


@with_test_settings
class IntegratedAgentViewSetTest(BaseTestMixin, APITestCase):
    """
    Tests for the integrated agent viewset.

    Tests the complete CRUD operations for integrated agents, including:
    - Listing integrated agents by project
    - Retrieving individual integrated agent details
    - Updating integrated agent configurations
    - Permission validation and authentication
    - Query parameter handling and validation
    """

    def setUp(self):
        super().setUp()

        self.project1 = Project.objects.create(name="Project 1", uuid=uuid4())
        self.project2 = Project.objects.create(name="Project 2", uuid=uuid4())

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

        self.agent_rule = AgentRule.objects.create(
            agent=self.agent1,
            slug="test-template-slug",
            uuid=uuid4(),
            name="Test Template",
            display_name="Test Template Display",
            start_condition="test_condition",
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

        self.user = User.objects.create_user(
            username="testuser", password="12345", email="test@example.com"
        )

        self.client.force_authenticate(self.user)
        self._setup_test_urls()

    def _setup_test_urls(self):
        """Configure common test URLs"""
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

    def _make_list_request(self, project_uuid=None):
        """
        Helper method to make list requests for integrated agents

        Args:
            project_uuid: Project UUID for the request header

        Returns:
            Response from the request
        """
        headers = {}
        if project_uuid:
            headers["HTTP_PROJECT_UUID"] = str(project_uuid)

        return self.client.get(self.list_url, **headers)

    def _make_detail_request(
        self, integrated_agent_uuid, project_uuid=None, query_params=None
    ):
        """
        Helper method to make detail requests for integrated agents

        Args:
            integrated_agent_uuid: UUID of the integrated agent
            project_uuid: Project UUID for the request header
            query_params: Additional query parameters

        Returns:
            Response from the request
        """
        url = reverse("assigned-agents-detail", args=[str(integrated_agent_uuid)])

        if query_params:
            query_string = "&".join([f"{k}={v}" for k, v in query_params.items()])
            url = f"{url}?{query_string}"

        headers = {}
        if project_uuid:
            headers["HTTP_PROJECT_UUID"] = str(project_uuid)

        return self.client.get(url, **headers)

    def _make_patch_request(
        self, integrated_agent_uuid, data, project_uuid=None, user_email=None
    ):
        """
        Helper method to make patch requests for integrated agents

        Args:
            integrated_agent_uuid: UUID of the integrated agent
            data: Data to update
            project_uuid: Project UUID for the request header
            user_email: User email for query parameter

        Returns:
            Response from the request
        """
        url = reverse("assigned-agents-detail", args=[str(integrated_agent_uuid)])

        if user_email:
            url = f"{url}?user_email={user_email}"

        headers = {}
        if project_uuid:
            headers["HTTP_PROJECT_UUID"] = str(project_uuid)

        return self.client.patch(url, data=data, **headers)

    def _create_template(self, name, integrated_agent, is_active=True, deleted_at=None):
        """
        Helper method to create templates for testing

        Args:
            name: Template name
            integrated_agent: Associated integrated agent
            is_active: Whether template is active
            deleted_at: Deletion timestamp (optional)

        Returns:
            Created template instance
        """
        return Template.objects.create(
            uuid=uuid4(),
            name=name,
            integrated_agent=integrated_agent,
            parent=self.agent_rule,
            is_active=is_active,
            deleted_at=deleted_at,
        )

    @patch("retail.agents.domains.agent_integration.views.ListIntegratedAgentUseCase")
    def test_list_integrated_agents_with_valid_project_uuid(self, mock_use_case_class):
        """Test listing integrated agents with valid project UUID"""
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = [
            self.integrated_agent1,
            self.integrated_agent2,
        ]
        mock_use_case_class.return_value = mock_use_case

        response = self._make_list_request(project_uuid=self.project1.uuid)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once_with(str(self.project1.uuid))

        returned_uuids = {agent["uuid"] for agent in response.json()}
        self.assertIn(str(self.integrated_agent1.uuid), returned_uuids)
        self.assertIn(str(self.integrated_agent2.uuid), returned_uuids)

    def test_list_integrated_agents_missing_project_uuid_header(self):
        """Test listing integrated agents fails when Project-UUID header is missing"""
        response = self._make_list_request()
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(
        "retail.agents.domains.agent_integration.views.RetrieveIntegratedAgentUseCase"
    )
    def test_retrieve_integrated_agent_with_permission(self, mock_use_case):
        """Test retrieving integrated agent with proper permissions"""
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent1,
            project=self.project1,
        )
        mock_use_case.return_value.execute.return_value = integrated_agent

        user = User.objects.create_user(username="test_user", password="password")
        self.client.force_authenticate(user)

        response = self._make_detail_request(
            integrated_agent.uuid, project_uuid=self.project1.uuid
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.return_value.execute.assert_called_once_with(
            str(integrated_agent.uuid), {"show_all": False, "start": None, "end": None}
        )

    @patch(
        "retail.agents.domains.agent_integration.views.RetrieveIntegratedAgentUseCase"
    )
    def test_retrieve_integrated_agent_with_show_all_query_param(self, mock_use_case):
        """Test retrieving integrated agent with show_all parameter"""
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent1,
            project=self.project1,
        )
        mock_use_case.return_value.execute.return_value = integrated_agent

        user = User.objects.create_user(username="test_user", password="password")
        self.client.force_authenticate(user)

        response = self._make_detail_request(
            integrated_agent.uuid,
            project_uuid=self.project1.uuid,
            query_params={"show_all": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.return_value.execute.assert_called_once_with(
            str(integrated_agent.uuid), {"show_all": True, "start": None, "end": None}
        )

    @patch(
        "retail.agents.domains.agent_integration.views.RetrieveIntegratedAgentUseCase"
    )
    def test_retrieve_integrated_agent_with_date_range_query_params(
        self, mock_use_case_class
    ):
        """Test retrieving integrated agent with date range parameters"""
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = self.integrated_agent1
        mock_use_case_class.return_value = mock_use_case

        response = self._make_detail_request(
            self.integrated_agent1.uuid,
            project_uuid=self.project1.uuid,
            query_params={
                "show_all": "true",
                "start": "2024-01-01",
                "end": "2024-01-31",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["uuid"], str(self.integrated_agent1.uuid))
        mock_use_case.execute.assert_called_once_with(
            str(self.integrated_agent1.uuid),
            {"show_all": True, "start": "2024-01-01", "end": "2024-01-31"},
        )

    def test_retrieve_integrated_agent_invalid_query_params(self):
        """Test retrieving integrated agent with invalid query parameters"""
        response = self._make_detail_request(
            self.integrated_agent1.uuid,
            project_uuid=self.project1.uuid,
            query_params={"start": "invalid-date"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(
        "retail.agents.domains.agent_integration.views.RetrieveIntegratedAgentUseCase"
    )
    def test_retrieve_integrated_agent_without_permission(self, mock_use_case_class):
        """Test retrieving integrated agent fails without proper permissions"""
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = self.integrated_agent3
        mock_use_case_class.return_value = mock_use_case

        response = self._make_detail_request(
            self.integrated_agent3.uuid, project_uuid=self.project1.uuid
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_integrated_agent_missing_project_uuid_header(self):
        """Test retrieving integrated agent fails when Project-UUID header is missing"""
        response = self._make_detail_request(self.integrated_agent1.uuid)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch("retail.agents.domains.agent_integration.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_integrated_agent_success(self, mock_use_case_class):
        """Test successful partial update of integrated agent with contributor permissions"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

        mock_use_case = MagicMock()
        updated_agent = self.integrated_agent1
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent1
        mock_use_case.execute.return_value = updated_agent
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self._make_patch_request(
            self.integrated_agent1.uuid,
            data=update_data,
            project_uuid=self.project1.uuid,
            user_email="test@example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once()
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    @patch("retail.agents.domains.agent_integration.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_insufficient_project_permissions(self, mock_use_case_class):
        """Test partial update fails with insufficient permissions"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent1
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self._make_patch_request(
            self.integrated_agent1.uuid,
            data=update_data,
            project_uuid=self.project1.uuid,
            user_email="test@example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_use_case.execute.assert_not_called()
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    @patch("retail.agents.domains.agent_integration.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_connect_service_error(self, mock_use_case_class):
        """Test partial update fails when ConnectService returns error"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            *ConnectServicePermissionScenarios.USER_NOT_FOUND
        )

        mock_use_case = MagicMock()
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent1
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self._make_patch_request(
            self.integrated_agent1.uuid,
            data=update_data,
            project_uuid=self.project1.uuid,
            user_email="test@example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_use_case.execute.assert_not_called()
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    @patch("retail.agents.domains.agent_integration.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_moderator_permissions_success(self, mock_use_case_class):
        """Test successful partial update with moderator permissions"""
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.MODERATOR_PERMISSIONS,
        )

        mock_use_case = MagicMock()
        updated_agent = self.integrated_agent1
        mock_use_case.get_integrated_agent.return_value = self.integrated_agent1
        mock_use_case.execute.return_value = updated_agent
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self._make_patch_request(
            self.integrated_agent1.uuid,
            data=update_data,
            project_uuid=self.project1.uuid,
            user_email="test@example.com",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once()
        self._mock_connect_instance.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    def test_partial_update_missing_user_email_query_param(self):
        """Test partial update fails when user_email parameter is missing"""
        self.setup_internal_user_permissions(self.user)

        update_data = {"contact_percentage": 20}

        response = self._make_patch_request(
            self.integrated_agent1.uuid,
            data=update_data,
            project_uuid=self.project1.uuid,
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_partial_update_integrated_agent_missing_project_uuid_header(self):
        """Test partial update fails when Project-UUID header is missing"""
        update_data = {"contact_percentage": 20}

        response = self._make_patch_request(
            self.integrated_agent1.uuid, data=update_data
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_access(self):
        """Test that unauthenticated users cannot access integrated agents"""
        self.client.force_authenticate(None)

        response = self._make_list_request(project_uuid=self.project1.uuid)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_integration_retrieve_with_default_params_returns_active_templates_only(
        self,
    ):
        """Test retrieve returns only active templates by default"""
        self._create_template(
            "Active Template 1", self.integrated_agent1, is_active=True
        )
        self._create_template(
            "Active Template 2", self.integrated_agent1, is_active=True
        )
        self._create_template(
            "Inactive Template", self.integrated_agent1, is_active=False
        )

        response = self._make_detail_request(
            self.integrated_agent1.uuid, project_uuid=self.project1.uuid
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        templates = response_data["templates"]
        self.assertEqual(len(templates), 2)

        template_names = [template["name"] for template in templates]
        self.assertIn("Active Template 1", template_names)
        self.assertIn("Active Template 2", template_names)
        self.assertNotIn("Inactive Template", template_names)

    def test_integration_retrieve_with_show_all_true_returns_all_templates(self):
        """Test retrieve returns all templates when show_all is true"""
        self._create_template(
            "Active Template 1", self.integrated_agent1, is_active=True
        )
        self._create_template(
            "Inactive Template", self.integrated_agent1, is_active=False
        )

        response = self._make_detail_request(
            self.integrated_agent1.uuid,
            project_uuid=self.project1.uuid,
            query_params={"show_all": "true"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        templates = response_data["templates"]
        self.assertEqual(len(templates), 2)

        template_names = [template["name"] for template in templates]
        self.assertIn("Active Template 1", template_names)
        self.assertIn("Inactive Template", template_names)

    def test_integration_retrieve_with_date_range_excludes_deleted_in_range(self):
        """Test retrieve excludes templates deleted within date range"""
        self._create_template("Active Template", self.integrated_agent1, is_active=True)
        self._create_template(
            "Deleted Template",
            self.integrated_agent1,
            is_active=False,
            deleted_at=datetime(2024, 1, 15, 10, 0, 0),
        )

        response = self._make_detail_request(
            self.integrated_agent1.uuid,
            project_uuid=self.project1.uuid,
            query_params={
                "show_all": "true",
                "start": "2024-01-01",
                "end": "2024-01-31",
            },
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        templates = response_data["templates"]
        self.assertEqual(len(templates), 1)

        template_names = [template["name"] for template in templates]
        self.assertIn("Active Template", template_names)
        self.assertNotIn("Deleted Template", template_names)

    def test_integration_validation_error_start_without_end(self):
        """Test validation error when start date provided without end date"""
        response = self._make_detail_request(
            self.integrated_agent1.uuid,
            project_uuid=self.project1.uuid,
            query_params={"start": "2024-01-01"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_end", response.json())

    def test_integration_validation_error_date_range_without_show_all(self):
        """Test validation error when date range provided without show_all"""
        response = self._make_detail_request(
            self.integrated_agent1.uuid,
            project_uuid=self.project1.uuid,
            query_params={"start": "2024-01-01", "end": "2024-01-31"},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("show_all", response.json())
