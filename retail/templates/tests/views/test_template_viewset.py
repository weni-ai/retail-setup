from uuid import uuid4

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from rest_framework.test import APITestCase, APIClient
from rest_framework.exceptions import NotFound
from rest_framework import status

from retail.agents.models import PreApprovedTemplate, Agent
from retail.templates.models import Template, Version
from retail.templates.usecases import (
    CreateTemplateUseCase,
    ReadTemplateUseCase,
    UpdateTemplateUseCase,
)
from retail.projects.models import Project

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

        self.create_usecase = CreateTemplateUseCase()
        self.read_usecase = ReadTemplateUseCase()
        self.update_usecase = UpdateTemplateUseCase()

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

        self.create_usecase_patch.start()
        self.read_usecase_patch.start()
        self.update_usecase_patch.start()

        self.addCleanup(self.create_usecase_patch.stop)
        self.addCleanup(self.read_usecase_patch.stop)
        self.addCleanup(self.update_usecase_patch.stop)

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
