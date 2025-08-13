from uuid import uuid4

from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils import timezone

from rest_framework.test import APITestCase, APIClient
from rest_framework.exceptions import NotFound
from rest_framework import status

from retail.agents.models import PreApprovedTemplate, Agent, IntegratedAgent
from retail.templates.models import Template, Version
from retail.templates.usecases import (
    CreateTemplateUseCase,
    ReadTemplateUseCase,
    UpdateTemplateUseCase,
    UpdateTemplateContentUseCase,
    DeleteTemplateUseCase,
    CreateCustomTemplateUseCase,
)
from retail.projects.models import Project
from retail.services.rule_generator import (
    RuleGeneratorUnprocessableEntity,
    RuleGeneratorBadRequest,
    RuleGeneratorInternalServerError,
)

User = get_user_model()

CONNECT_SERVICE_PATH = "retail.internal.permissions.ConnectService"


class TemplateViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@example.com"
        )

        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Projeto Teste",
        )

        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agente de Teste",
            slug="agente-teste",
            description="Agente para testes",
            is_oficial=True,
            lambda_arn=None,
            project=self.project,
            credentials={},
        )

        self.parent = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid4(),
            name="parent_template",
            display_name="Parent Template",
            content="Conteúdo do template",
            is_valid=True,
            start_condition="always",
            metadata={},
        )

        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(), agent=self.agent, project=self.project, is_active=True
        )

        self.create_usecase = CreateTemplateUseCase()
        self.read_usecase = ReadTemplateUseCase()
        self.update_usecase = UpdateTemplateUseCase()
        self.update_content_usecase = UpdateTemplateContentUseCase()
        self.delete_usecase = DeleteTemplateUseCase()
        self.create_custom_usecase = MagicMock(spec=CreateCustomTemplateUseCase)

        self.create_usecase_patch = patch(
            "retail.templates.views.CreateTemplateUseCase",
            return_value=self.create_usecase,
        )
        self.read_usecase_patch = patch(
            "retail.templates.views.ReadTemplateUseCase",
            return_value=self.read_usecase,
        )
        self.update_usecase_patch = patch(
            "retail.templates.views.UpdateTemplateUseCase",
            return_value=self.update_usecase,
        )
        self.update_content_usecase_patch = patch(
            "retail.templates.views.UpdateTemplateContentUseCase",
            return_value=self.update_content_usecase,
        )
        self.delete_usecase_patch = patch(
            "retail.templates.views.DeleteTemplateUseCase",
            return_value=self.delete_usecase,
        )
        self.create_custom_usecase_patch = patch(
            "retail.templates.views.CreateCustomTemplateUseCase",
            return_value=self.create_custom_usecase,
        )

        self.create_usecase_patch.start()
        self.read_usecase_patch.start()
        self.update_usecase_patch.start()
        self.update_content_usecase_patch.start()
        self.delete_usecase_patch.start()
        self.create_custom_usecase_patch.start()

        self.addCleanup(self.create_usecase_patch.stop)
        self.addCleanup(self.read_usecase_patch.stop)
        self.addCleanup(self.update_usecase_patch.stop)
        self.addCleanup(self.update_content_usecase_patch.stop)
        self.addCleanup(self.delete_usecase_patch.stop)
        self.addCleanup(self.create_custom_usecase_patch.stop)

    def _add_internal_permission_to_user(self):
        """Helper method to add can_communicate_internally permission to user"""
        content_type = ContentType.objects.get_for_model(User)
        permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="Can communicate internally",
            content_type=content_type,
        )
        self.user.user_permissions.add(permission)
        self.user.save()

    def _get_project_headers_and_params(self):
        """Helper method to get standard headers and params for HasProjectPermission"""
        return {"HTTP_PROJECT_UUID": str(self.project.uuid)}, {
            "user_email": self.user.email
        }

    @patch(CONNECT_SERVICE_PATH)
    def test_create_template(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )

        self.create_usecase.execute = lambda payload: template

        payload = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-list")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "PENDING")
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), self.user.email
        )

    @patch(CONNECT_SERVICE_PATH)
    def test_create_template_invalid_data(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        payload = {
            "template_name": "",
            "category": "test",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-list")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    def test_read_template(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )
        version = Version.objects.create(
            template=template,
            template_name="test_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        template.current_version = version
        template.save()

        self.read_usecase.execute = lambda uuid: template

        template_uuid = str(template.uuid)
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.get(url, **headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "APPROVED")

    @patch(CONNECT_SERVICE_PATH)
    def test_read_template_not_found(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.read_usecase.execute = lambda uuid: (_ for _ in ()).throw(
            NotFound("Template not found")
        )

        template_uuid = str(uuid4())
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.get(url, **headers)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_status(self):
        # Status action uses only CanCommunicateInternally permission (not HasProjectPermission)
        self._add_internal_permission_to_user()

        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )
        version = Version.objects.create(
            template=template,
            template_name="test_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="PENDING",
        )
        template.current_version = version
        template.save()

        def execute(payload):
            version.status = payload["status"]
            version.save()
            template.current_version = version
            template.save()
            return template

        self.update_usecase.execute = execute

        payload = {"version_uuid": str(version.uuid), "status": "APPROVED"}

        url = reverse("template-status")

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "APPROVED")

    def test_patch_status_not_found(self):
        # Status action uses only CanCommunicateInternally permission (not HasProjectPermission)
        self._add_internal_permission_to_user()

        self.update_usecase.execute = lambda payload: (_ for _ in ()).throw(
            NotFound("not found")
        )

        payload = {"version_uuid": str(uuid4()), "status": "APPROVED"}

        url = reverse("template-status")
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_status_invalid_data(self):
        # Status action uses only CanCommunicateInternally permission (not HasProjectPermission)
        self._add_internal_permission_to_user()

        payload = {"version_uuid": "invalid-uuid", "status": "INVALID_STATUS"}

        url = reverse("template-status")
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_template_content(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )
        version = Version.objects.create(
            template=template,
            template_name="test_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        template.current_version = version
        template.save()

        updated_template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )

        self.update_content_usecase.execute = lambda data: updated_template

        payload = {
            "template_body": "Updated template body with {{placeholder}}",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "parameters": None,
        }

        template_uuid = str(template.uuid)
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_template_content_with_custom_template_parameters(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        custom_template = Template.objects.create(
            uuid=uuid4(),
            name="custom_template",
            integrated_agent=self.integrated_agent,
        )
        version = Version.objects.create(
            template=custom_template,
            template_name="custom_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        custom_template.current_version = version
        custom_template.save()

        updated_template = Template.objects.create(
            uuid=uuid4(),
            name="custom_template",
            integrated_agent=self.integrated_agent,
        )

        self.update_content_usecase.execute = lambda data: updated_template

        payload = {
            "template_body": "Updated custom template body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "parameters": [
                {"name": "start_condition", "value": "user.is_active == true"},
                {
                    "name": "custom_logic",
                    "value": "if user.premium: send_premium_template()",
                },
            ],
        }

        template_uuid = str(custom_template.uuid)
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "custom_template")

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_template_content_invalid_data(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template_uuid = str(uuid4())
        payload = {
            "template_body": "",
            "app_uuid": str(uuid4()),
            "parameters": None,
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    def test_partial_update_template_content_not_found(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.update_content_usecase.execute = lambda data: (_ for _ in ()).throw(
            NotFound("Template not found")
        )

        payload = {
            "template_body": "Updated template body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "parameters": None,
        }

        template_uuid = str(uuid4())
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(CONNECT_SERVICE_PATH)
    def test_delete_template(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )

        self.delete_usecase.execute = MagicMock()

        template_uuid = str(template.uuid)
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.delete(url, **headers)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.delete_usecase.execute.assert_called_once_with(template_uuid)

    @patch(CONNECT_SERVICE_PATH)
    def test_delete_template_not_found(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.delete_usecase.execute = lambda uuid: (_ for _ in ()).throw(
            NotFound("Template not found")
        )

        template_uuid = str(uuid4())
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.delete(url, **headers)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_unauthorized_access(self):
        client = APIClient()

        response = client.get(reverse("template-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = client.post(reverse("template-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        template_uuid = str(uuid4())
        response = client.get(reverse("template-detail", args=[template_uuid]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_success(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="custom_template",
            display_name="Custom Template",
            integrated_agent=self.integrated_agent,
            rule_code="def custom_rule(): return True",
            metadata={"test": "data"},
        )

        self.create_custom_usecase.execute = lambda payload: template

        payload = {
            "template_translation": {
                "template_header": "Test Header",
                "template_body": "Test Body {{name}}",
                "template_footer": "Test Footer",
                "template_button": [{"type": "URL", "text": "Click here"}],
            },
            "template_name": "custom_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(self.integrated_agent.uuid),
            "parameters": [
                {
                    "name": "variables",
                    "value": '[{"definition": "name", "fallback": "User"}]',
                },
                {"name": "start_condition", "value": "always true"},
            ],
            "display_name": "Custom Template Display",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "custom_template")
        self.assertEqual(response.data["display_name"], "Custom Template")
        self.assertEqual(response.data["is_custom"], True)

    # ===== PERMISSION TESTS =====

    def test_missing_project_uuid_header_returns_403(self):
        """Test that missing Project-Uuid header returns 403 for HasProjectPermission"""
        self._add_internal_permission_to_user()

        payload = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        # Missing Project-Uuid header
        response = self.client.post(
            reverse("template-list") + f"?user_email={self.user.email}",
            payload,
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    def test_missing_user_email_query_param_returns_403(self, mock_connect_service):
        """Test that missing user_email query param returns 403 for internal users"""
        self._add_internal_permission_to_user()

        payload = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        # Missing user_email query param
        response = self.client.post(
            reverse("template-list"),
            payload,
            format="json",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_connect_service.return_value.get_user_permissions.assert_not_called()

    @patch(CONNECT_SERVICE_PATH)
    def test_insufficient_project_permissions_returns_403(self, mock_connect_service):
        """Test that insufficient project permissions (not contributor/moderator) returns 403"""
        self._add_internal_permission_to_user()

        # User has only chat_user level (5), needs contributor (2) or moderator (3)
        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 5},  # chat_user level
        )

        payload = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-list")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_connect_service.return_value.get_user_permissions.assert_called_once_with(
            str(self.project.uuid), self.user.email
        )

    @patch(CONNECT_SERVICE_PATH)
    def test_connect_service_error_returns_403(self, mock_connect_service):
        """Test that Connect service errors return 403"""
        self._add_internal_permission_to_user()

        # Simulate Connect service returning error
        mock_connect_service.return_value.get_user_permissions.return_value = (
            404,
            {"error": "User not found"},
        )

        payload = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-list")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_status_action_without_internal_permission_returns_403(self):
        """Test that status action without CanCommunicateInternally permission returns 403"""
        # User without can_communicate_internally permission
        payload = {"version_uuid": str(uuid4()), "status": "APPROVED"}

        url = reverse("template-status")
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_status_action_with_internal_permission_works(self):
        """Test that status action works with CanCommunicateInternally permission"""
        self._add_internal_permission_to_user()

        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )
        version = Version.objects.create(
            template=template,
            template_name="test_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="PENDING",
        )
        template.current_version = version
        template.save()

        def execute(payload):
            version.status = payload["status"]
            version.save()
            template.current_version = version
            template.save()
            return template

        self.update_usecase.execute = execute

        payload = {"version_uuid": str(version.uuid), "status": "APPROVED"}
        url = reverse("template-status")

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "APPROVED")

    def test_unauthenticated_user_returns_403(self):
        """Test that unauthenticated users get 403"""
        self.client.force_authenticate(None)  # Remove authentication

        response = self.client.get(reverse("template-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.post(reverse("template-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        template_uuid = str(uuid4())
        response = self.client.get(reverse("template-detail", args=[template_uuid]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = self.client.patch(reverse("template-status"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_invalid_data(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        payload = {
            "template_translation": {"template_body": "Test Body"},
            "category": "custom",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_missing_required_fields(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        payload = {
            "template_translation": {"template_body": "Test Body"},
            "template_name": "test_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_integrated_agent_not_found(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.create_custom_usecase.execute = lambda payload: (_ for _ in ()).throw(
            NotFound("Assigned agent not found")
        )

        payload = {
            "template_translation": {
                "template_header": "Test Header",
                "template_body": "Test Body",
                "template_footer": "Test Footer",
            },
            "template_name": "custom_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(uuid4()),
            "parameters": [{"name": "start_condition", "value": "test condition"}],
            "display_name": "Custom Template",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_code_generator_bad_request(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.create_custom_usecase.execute = lambda payload: (_ for _ in ()).throw(
            RuleGeneratorBadRequest(detail={"error": "Invalid parameters"})
        )

        payload = {
            "template_translation": {"template_body": "Test Body"},
            "template_name": "custom_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(self.integrated_agent.uuid),
            "parameters": [{"name": "invalid_param", "value": "invalid_value"}],
            "display_name": "Custom Template",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_code_generator_unprocessable_entity(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.create_custom_usecase.execute = lambda payload: (_ for _ in ()).throw(
            RuleGeneratorUnprocessableEntity(detail={"error": "Cannot process request"})
        )

        payload = {
            "template_translation": {"template_body": "Test Body"},
            "template_name": "custom_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(self.integrated_agent.uuid),
            "parameters": [{"name": "complex_param", "value": "unprocessable_value"}],
            "display_name": "Custom Template",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_code_generator_internal_server_error(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        self.create_custom_usecase.execute = lambda payload: (_ for _ in ()).throw(
            RuleGeneratorInternalServerError(
                detail={"message": "Internal lambda error"}
            )
        )

        payload = {
            "template_translation": {"template_body": "Test Body"},
            "template_name": "custom_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(self.integrated_agent.uuid),
            "parameters": [{"name": "start_condition", "value": "test condition"}],
            "display_name": "Custom Template",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    @patch(CONNECT_SERVICE_PATH)
    def test_create_custom_template_with_buttons(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="custom_template_with_buttons",
            display_name="Custom Template with Buttons",
            integrated_agent=self.integrated_agent,
            metadata={"buttons": [{"type": "URL", "text": "Visit Site"}]},
        )

        self.create_custom_usecase.execute = lambda payload: template

        payload = {
            "template_translation": {
                "template_body": "Check out our site!",
                "template_button": [
                    {"type": "URL", "text": "Visit Site", "url": "https://example.com"}
                ],
            },
            "template_name": "custom_template_with_buttons",
            "category": "marketing",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(self.integrated_agent.uuid),
            "parameters": [{"name": "start_condition", "value": "user_interested"}],
            "display_name": "Marketing Template",
        }

        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-custom")
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.post(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn("metadata", response.data)
        if "buttons" in response.data["metadata"]:
            self.assertIn("type", response.data["metadata"]["buttons"][0])

    def test_create_custom_template_unauthorized(self):
        client = APIClient()

        payload = {
            "template_translation": {"template_body": "Test Body"},
            "template_name": "custom_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(self.integrated_agent.uuid),
            "parameters": [],
            "display_name": "Custom Template",
        }

        url = reverse("template-custom")
        response = client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_create_custom_template_without_permission(self):
        user_without_permission = User.objects.create_user(
            username="nopermuser", password="testpass"
        )
        client = APIClient()
        client.force_authenticate(user=user_without_permission)

        payload = {
            "template_translation": {"template_body": "Test Body"},
            "template_name": "custom_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "integrated_agent_uuid": str(self.integrated_agent.uuid),
            "parameters": [],
            "display_name": "Custom Template",
        }

        url = reverse("template-custom")
        response = client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_forbidden_access_without_permission(self):
        user_without_permission = User.objects.create_user(
            username="nopermuser", password="testpass"
        )
        client = APIClient()
        client.force_authenticate(user=user_without_permission)

        response = client.get(reverse("template-list"))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        response = client.post(reverse("template-list"), {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

        template_uuid = str(uuid4())
        response = client.get(reverse("template-detail", args=[template_uuid]))
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @patch(CONNECT_SERVICE_PATH)
    def test_integration_delete_template_successfully(self, mock_connect_service):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            ignore_templates=[],
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="Test Template",
            integrated_agent=integrated_agent,
            parent=self.parent,
            is_active=True,
            deleted_at=None,
        )

        with patch("retail.templates.views.DeleteTemplateUseCase") as mock_delete_class:
            real_delete_usecase = DeleteTemplateUseCase()
            mock_delete_class.return_value = real_delete_usecase

            headers, params = self._get_project_headers_and_params()
            url = (
                reverse("template-detail", args=[str(template.uuid)])
                + "?"
                + "&".join([f"{k}={v}" for k, v in params.items()])
            )

            before_execution = timezone.now()
            response = self.client.delete(url, **headers)
            after_execution = timezone.now()

            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            template.refresh_from_db()

            self.assertFalse(template.is_active)

            self.assertIsNotNone(template.deleted_at)
            self.assertGreaterEqual(template.deleted_at, before_execution)
            self.assertLessEqual(template.deleted_at, after_execution)

            integrated_agent.refresh_from_db()
            self.assertIn(self.parent.slug, integrated_agent.ignore_templates)

    @patch(CONNECT_SERVICE_PATH)
    def test_integration_delete_nonexistent_template_returns_not_found(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        with patch("retail.templates.views.DeleteTemplateUseCase") as mock_delete_class:
            real_delete_usecase = DeleteTemplateUseCase()
            mock_delete_class.return_value = real_delete_usecase

            fake_uuid = str(uuid4())
            headers, params = self._get_project_headers_and_params()
            url = (
                reverse("template-detail", args=[fake_uuid])
                + "?"
                + "&".join([f"{k}={v}" for k, v in params.items()])
            )

            response = self.client.delete(url, **headers)

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(CONNECT_SERVICE_PATH)
    def test_integration_delete_inactive_template_returns_not_found(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="Inactive Template",
            parent=self.parent,
            is_active=False,
        )

        with patch("retail.templates.views.DeleteTemplateUseCase") as mock_delete_class:
            real_delete_usecase = DeleteTemplateUseCase()
            mock_delete_class.return_value = real_delete_usecase

            headers, params = self._get_project_headers_and_params()
            url = (
                reverse("template-detail", args=[str(template.uuid)])
                + "?"
                + "&".join([f"{k}={v}" for k, v in params.items()])
            )

            response = self.client.delete(url, **headers)

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    @patch(CONNECT_SERVICE_PATH)
    def test_integration_delete_template_updates_ignore_list(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            ignore_templates=["existing-template"],
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="Test Template",
            integrated_agent=integrated_agent,
            parent=self.parent,
            is_active=True,
        )

        with patch("retail.templates.views.DeleteTemplateUseCase") as mock_delete_class:
            real_delete_usecase = DeleteTemplateUseCase()
            mock_delete_class.return_value = real_delete_usecase

            initial_ignore_count = len(integrated_agent.ignore_templates)

            headers, params = self._get_project_headers_and_params()
            url = (
                reverse("template-detail", args=[str(template.uuid)])
                + "?"
                + "&".join([f"{k}={v}" for k, v in params.items()])
            )

            response = self.client.delete(url, **headers)

            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            integrated_agent.refresh_from_db()
            self.assertEqual(
                len(integrated_agent.ignore_templates), initial_ignore_count + 1
            )
            self.assertIn(self.parent.slug, integrated_agent.ignore_templates)
            self.assertIn("existing-template", integrated_agent.ignore_templates)

    @patch(CONNECT_SERVICE_PATH)
    def test_integration_delete_preserves_other_template_fields(
        self, mock_connect_service
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            channel_uuid=uuid4(),
            is_active=True,
            ignore_templates=[],
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="Test Template",
            integrated_agent=integrated_agent,
            parent=self.parent,
            is_active=True,
        )

        original_name = template.name
        original_uuid = template.uuid

        with patch("retail.templates.views.DeleteTemplateUseCase") as mock_delete_class:
            real_delete_usecase = DeleteTemplateUseCase()
            mock_delete_class.return_value = real_delete_usecase

            headers, params = self._get_project_headers_and_params()
            url = (
                reverse("template-detail", args=[str(template.uuid)])
                + "?"
                + "&".join([f"{k}={v}" for k, v in params.items()])
            )

            response = self.client.delete(url, **headers)

            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            template.refresh_from_db()
            self.assertEqual(template.name, original_name)
            self.assertEqual(template.uuid, original_uuid)
            self.assertFalse(template.is_active)
            self.assertIsNotNone(template.deleted_at)
