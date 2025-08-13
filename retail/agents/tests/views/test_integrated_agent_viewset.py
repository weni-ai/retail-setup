from unittest.mock import patch, MagicMock

from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from datetime import datetime

from django.urls import reverse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission, ContentType

from uuid import uuid4

from retail.agents.models import IntegratedAgent, Agent, PreApprovedTemplate
from retail.projects.models import Project
from retail.templates.models import Template

User = get_user_model()

CONNECT_SERVICE_PATH = "retail.internal.permissions.ConnectService"


class IntegratedAgentViewSetTest(APITestCase):
    def setUp(self):
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

        self.pre_approved_template = PreApprovedTemplate.objects.create(
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

        content_type = ContentType.objects.get_for_model(User)
        self.permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="Can Communicate Internally",
            content_type=content_type,
        )
        self.user.user_permissions.add(self.permission)
        self.user.save()

        self.client = APIClient()
        self.client.force_authenticate(self.user)

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

    @patch("retail.agents.views.ListIntegratedAgentUseCase")
    def test_list_integrated_agents_with_valid_project_uuid(self, mock_use_case_class):
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = [
            self.integrated_agent1,
            self.integrated_agent2,
        ]
        mock_use_case_class.return_value = mock_use_case

        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once_with(str(self.project1.uuid))

        returned_uuids = {agent["uuid"] for agent in response.json()}
        self.assertIn(str(self.integrated_agent1.uuid), returned_uuids)
        self.assertIn(str(self.integrated_agent2.uuid), returned_uuids)

    def test_list_integrated_agents_missing_project_uuid_header(self):
        response = self.client.get(self.list_url)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    @patch("retail.agents.views.RetrieveIntegratedAgentUseCase")
    def test_retrieve_integrated_agent_with_permission(self, mock_use_case):
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent1,
            project=self.project1,
        )
        mock_use_case.return_value.execute.return_value = integrated_agent

        user = User.objects.create_user(username="test_user", password="password")

        self.client.force_authenticate(user)

        url = reverse("assigned-agents-detail", args=[str(integrated_agent.uuid)])

        response = self.client.get(url, HTTP_PROJECT_UUID=str(self.project1.uuid))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.return_value.execute.assert_called_once_with(
            str(integrated_agent.uuid), {"show_all": False, "start": None, "end": None}
        )

    @patch("retail.agents.views.RetrieveIntegratedAgentUseCase")
    def test_retrieve_integrated_agent_with_show_all_query_param(self, mock_use_case):
        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent1,
            project=self.project1,
        )
        mock_use_case.return_value.execute.return_value = integrated_agent

        user = User.objects.create_user(username="test_user", password="password")

        self.client.force_authenticate(user)

        url = reverse("assigned-agents-detail", args=[str(integrated_agent.uuid)])

        response = self.client.get(
            url,
            {"show_all": "true"},
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.return_value.execute.assert_called_once_with(
            str(integrated_agent.uuid), {"show_all": True, "start": None, "end": None}
        )

    @patch("retail.agents.views.RetrieveIntegratedAgentUseCase")
    def test_retrieve_integrated_agent_with_date_range_query_params(
        self, mock_use_case_class
    ):
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = self.integrated_agent1
        mock_use_case_class.return_value = mock_use_case

        response = self.client.get(
            f"{self.detail_url1}?show_all=true&start=2024-01-01&end=2024-01-31",
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["uuid"], str(self.integrated_agent1.uuid))
        mock_use_case.execute.assert_called_once_with(
            str(self.integrated_agent1.uuid),
            {"show_all": True, "start": "2024-01-01", "end": "2024-01-31"},
        )

    def test_retrieve_integrated_agent_invalid_query_params(self):
        response = self.client.get(
            f"{self.detail_url1}?start=invalid-date",
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("retail.agents.views.RetrieveIntegratedAgentUseCase")
    def test_retrieve_integrated_agent_without_permission(self, mock_use_case_class):
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = self.integrated_agent3
        mock_use_case_class.return_value = mock_use_case

        response = self.client.get(
            self.detail_url3, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_retrieve_integrated_agent_missing_project_uuid_header(self):
        response = self.client.get(self.detail_url1)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.json(), {"project_uuid": "Missing project uuid in header."}
        )

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_integrated_agent_success(
        self, mock_use_case_class, mock_connect_service
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},
        )

        mock_use_case = MagicMock()
        updated_agent = self.integrated_agent1
        mock_use_case.execute.return_value = updated_agent
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self.client.patch(
            self.detail_url1 + "?user_email=test@example.com",
            data=update_data,
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once()
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_insufficient_project_permissions(
        self, mock_use_case_class, mock_connect_service
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 1},
        )

        mock_use_case = MagicMock()
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self.client.patch(
            self.detail_url1 + "?user_email=test@example.com",
            data=update_data,
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_use_case.execute.assert_not_called()
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_connect_service_error(
        self, mock_use_case_class, mock_connect_service
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            404,
            {"error": "Not found"},
        )

        mock_use_case = MagicMock()
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self.client.patch(
            self.detail_url1 + "?user_email=test@example.com",
            data=update_data,
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_use_case.execute.assert_not_called()
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.agents.views.UpdateIntegratedAgentUseCase")
    def test_partial_update_moderator_permissions_success(
        self, mock_use_case_class, mock_connect_service
    ):
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 3},
        )

        mock_use_case = MagicMock()
        updated_agent = self.integrated_agent1
        mock_use_case.execute.return_value = updated_agent
        mock_use_case_class.return_value = mock_use_case

        update_data = {"contact_percentage": 20}

        response = self.client.patch(
            self.detail_url1 + "?user_email=test@example.com",
            data=update_data,
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        mock_use_case.execute.assert_called_once()
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project1.uuid), "test@example.com"
        )

    def test_partial_update_missing_user_email_query_param(self):
        update_data = {"contact_percentage": 20}

        response = self.client.patch(
            self.detail_url1,
            data=update_data,
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_partial_update_integrated_agent_missing_project_uuid_header(self):
        update_data = {"contact_percentage": 20}

        response = self.client.patch(self.detail_url1, data=update_data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_unauthenticated_access(self):
        self.client.logout()

        response = self.client.get(
            self.list_url, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        response = self.client.get(
            self.detail_url1, HTTP_PROJECT_UUID=str(self.project1.uuid)
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_integration_retrieve_with_default_params_returns_active_templates_only(
        self,
    ):
        Template.objects.create(
            uuid=uuid4(),
            name="Active Template 1",
            integrated_agent=self.integrated_agent1,
            parent=self.pre_approved_template,
            is_active=True,
        )

        Template.objects.create(
            uuid=uuid4(),
            name="Active Template 2",
            integrated_agent=self.integrated_agent1,
            parent=self.pre_approved_template,
            is_active=True,
        )

        Template.objects.create(
            uuid=uuid4(),
            name="Inactive Template",
            integrated_agent=self.integrated_agent1,
            parent=self.pre_approved_template,
            is_active=False,
        )

        response = self.client.get(
            self.detail_url1, HTTP_PROJECT_UUID=str(self.project1.uuid)
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
        Template.objects.create(
            uuid=uuid4(),
            name="Active Template 1",
            integrated_agent=self.integrated_agent1,
            parent=self.pre_approved_template,
            is_active=True,
        )

        Template.objects.create(
            uuid=uuid4(),
            name="Inactive Template",
            integrated_agent=self.integrated_agent1,
            parent=self.pre_approved_template,
            is_active=False,
        )

        response = self.client.get(
            f"{self.detail_url1}?show_all=true",
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        templates = response_data["templates"]
        self.assertEqual(len(templates), 2)

        template_names = [template["name"] for template in templates]
        self.assertIn("Active Template 1", template_names)
        self.assertIn("Inactive Template", template_names)

    def test_integration_retrieve_with_date_range_excludes_deleted_in_range(self):
        Template.objects.create(
            uuid=uuid4(),
            name="Active Template",
            integrated_agent=self.integrated_agent1,
            parent=self.pre_approved_template,
            is_active=True,
        )

        Template.objects.create(
            uuid=uuid4(),
            name="Deleted Template",
            integrated_agent=self.integrated_agent1,
            parent=self.pre_approved_template,
            is_active=False,
            deleted_at=datetime(2024, 1, 15, 10, 0, 0),
        )

        response = self.client.get(
            f"{self.detail_url1}?show_all=true&start=2024-01-01&end=2024-01-31",
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response_data = response.json()

        templates = response_data["templates"]
        self.assertEqual(len(templates), 1)

        template_names = [template["name"] for template in templates]
        self.assertIn("Active Template", template_names)
        self.assertNotIn("Deleted Template", template_names)

    def test_integration_validation_error_start_without_end(self):
        response = self.client.get(
            f"{self.detail_url1}?start=2024-01-01",
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("start_end", response.json())

    def test_integration_validation_error_date_range_without_show_all(self):
        response = self.client.get(
            f"{self.detail_url1}?start=2024-01-01&end=2024-01-31",
            HTTP_PROJECT_UUID=str(self.project1.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("show_all", response.json())
