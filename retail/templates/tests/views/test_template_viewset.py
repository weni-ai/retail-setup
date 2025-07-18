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


class TemplateViewSetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="testuser", password="testpass")
        content_type = ContentType.objects.get_for_model(User)
        permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            name="Can communicate internally",
            content_type=content_type,
        )
        self.user.user_permissions.add(permission)
        self.user.save()

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

    def test_create_template(self):
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

        response = self.client.post(reverse("template-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "PENDING")

    def test_create_template_invalid_data(self):
        payload = {
            "template_name": "",
            "category": "test",
        }

        response = self.client.post(reverse("template-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_read_template(self):
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
        response = self.client.get(reverse("template-detail", args=[template_uuid]))

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "APPROVED")

    def test_read_template_not_found(self):
        self.read_usecase.execute = lambda uuid: (_ for _ in ()).throw(
            NotFound("Template not found")
        )

        template_uuid = str(uuid4())
        response = self.client.get(reverse("template-detail", args=[template_uuid]))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_status(self):
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
        self.update_usecase.execute = lambda payload: (_ for _ in ()).throw(
            NotFound("not found")
        )

        payload = {"version_uuid": str(uuid4()), "status": "APPROVED"}

        url = reverse("template-status")
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_patch_status_invalid_data(self):
        payload = {"version_uuid": "invalid-uuid", "status": "INVALID_STATUS"}

        url = reverse("template-status")
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_template_content(self):
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
        response = self.client.patch(
            reverse("template-detail", args=[template_uuid]), payload, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")

    def test_partial_update_template_content_with_custom_template_parameters(self):
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
        response = self.client.patch(
            reverse("template-detail", args=[template_uuid]), payload, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "custom_template")

    def test_partial_update_template_content_invalid_data(self):
        template_uuid = str(uuid4())
        payload = {
            "template_body": "",
            "app_uuid": str(uuid4()),
            "parameters": None,
        }

        response = self.client.patch(
            reverse("template-detail", args=[template_uuid]), payload, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_template_content_not_found(self):
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
        response = self.client.patch(
            reverse("template-detail", args=[template_uuid]), payload, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_delete_template(self):
        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )

        self.delete_usecase.execute = MagicMock()

        template_uuid = str(template.uuid)
        response = self.client.delete(reverse("template-detail", args=[template_uuid]))

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.delete_usecase.execute.assert_called_once_with(template_uuid)

    def test_delete_template_not_found(self):
        self.delete_usecase.execute = lambda uuid: (_ for _ in ()).throw(
            NotFound("Template not found")
        )

        template_uuid = str(uuid4())
        response = self.client.delete(reverse("template-detail", args=[template_uuid]))

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

    def test_create_custom_template_success(self):
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

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "custom_template")
        self.assertEqual(response.data["display_name"], "Custom Template")
        self.assertEqual(response.data["is_custom"], True)

    def test_create_custom_template_invalid_data(self):
        payload = {
            "template_translation": {"template_body": "Test Body"},
            "category": "custom",
        }

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_custom_template_missing_required_fields(self):
        payload = {
            "template_translation": {"template_body": "Test Body"},
            "template_name": "test_template",
            "category": "custom",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_custom_template_integrated_agent_not_found(self):
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

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_custom_template_code_generator_bad_request(self):
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

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_custom_template_code_generator_unprocessable_entity(self):
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

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)

    def test_create_custom_template_code_generator_internal_server_error(self):
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

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)

    def test_create_custom_template_with_buttons(self):
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

        url = reverse("template-custom")
        response = self.client.post(url, payload, format="json")

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

    def test_integration_delete_template_successfully(self):
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

            before_execution = timezone.now()
            response = self.client.delete(
                reverse("template-detail", args=[str(template.uuid)])
            )
            after_execution = timezone.now()

            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            template.refresh_from_db()

            self.assertFalse(template.is_active)

            self.assertIsNotNone(template.deleted_at)
            self.assertGreaterEqual(template.deleted_at, before_execution)
            self.assertLessEqual(template.deleted_at, after_execution)

            integrated_agent.refresh_from_db()
            self.assertIn(self.parent.slug, integrated_agent.ignore_templates)

    def test_integration_delete_nonexistent_template_returns_not_found(self):
        with patch("retail.templates.views.DeleteTemplateUseCase") as mock_delete_class:
            real_delete_usecase = DeleteTemplateUseCase()
            mock_delete_class.return_value = real_delete_usecase

            fake_uuid = str(uuid4())
            response = self.client.delete(reverse("template-detail", args=[fake_uuid]))

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_integration_delete_inactive_template_returns_not_found(self):
        template = Template.objects.create(
            uuid=uuid4(),
            name="Inactive Template",
            parent=self.parent,
            is_active=False,
        )

        with patch("retail.templates.views.DeleteTemplateUseCase") as mock_delete_class:
            real_delete_usecase = DeleteTemplateUseCase()
            mock_delete_class.return_value = real_delete_usecase

            response = self.client.delete(
                reverse("template-detail", args=[str(template.uuid)])
            )

            self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_integration_delete_template_updates_ignore_list(self):
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

            response = self.client.delete(
                reverse("template-detail", args=[str(template.uuid)])
            )

            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            integrated_agent.refresh_from_db()
            self.assertEqual(
                len(integrated_agent.ignore_templates), initial_ignore_count + 1
            )
            self.assertIn(self.parent.slug, integrated_agent.ignore_templates)
            self.assertIn("existing-template", integrated_agent.ignore_templates)

    def test_integration_delete_preserves_other_template_fields(self):
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

            response = self.client.delete(
                reverse("template-detail", args=[str(template.uuid)])
            )

            self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

            template.refresh_from_db()
            self.assertEqual(template.name, original_name)
            self.assertEqual(template.uuid, original_uuid)
            self.assertFalse(template.is_active)
            self.assertIsNotNone(template.deleted_at)
