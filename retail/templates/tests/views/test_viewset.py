from uuid import uuid4
from unittest.mock import Mock, patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from rest_framework.test import APITestCase, APIClient
from rest_framework.exceptions import NotFound
from rest_framework import status

from retail.templates.models import Template
from retail.templates.usecases import (
    CreateTemplateUseCase,
    ReadTemplateUseCase,
    UpdateTemplateUseCase,
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
        mock_template = Mock(spec=Template)
        mock_template.uuid = uuid4()
        mock_template.name = "test_template"
        mock_template.start_condition = "start"
        mock_template.current_version = None
        mock_template.metadata = {}

        self.create_usecase.execute = Mock(return_value=mock_template)

        payload = {
            "template_translation": {"en": {"text": "Hello"}},
            "template_name": "test_template",
            "start_condition": "start",
            "category": "test",
            "app_uuid": str(uuid4()),
            "project_uuid": str(uuid4()),
        }

        response = self.client.post(reverse("template-list"), payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "PENDING")
        self.create_usecase.execute.assert_called_once_with(payload)

    def test_read_template(self):
        mock_template = Mock(spec=Template)
        mock_template.uuid = uuid4()
        mock_template.name = "test_template"
        mock_template.start_condition = "start"
        mock_template.metadata = {}

        mock_version = Mock()
        mock_version.status = "APPROVED"
        mock_template.current_version = mock_version

        self.read_usecase.execute = Mock(return_value=mock_template)

        template_uuid = str(mock_template.uuid)
        response = self.client.get(
            reverse("template-detail", args=[str(template_uuid)])
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "APPROVED")
        self.read_usecase.execute.assert_called_once_with(template_uuid)

    def test_patch_status(self):
        mock_template = Mock(spec=Template)
        mock_template.uuid = uuid4()
        mock_template.name = "test_template"
        mock_template.start_condition = "start"
        mock_template.metadata = {}

        version_uuid = uuid4()

        mock_version = Mock()
        mock_version.uuid = version_uuid
        mock_version.status = "APPROVED"
        mock_template.current_version = mock_version

        self.update_usecase.execute = Mock(return_value=mock_template)

        payload = {"version_uuid": str(version_uuid), "status": "APPROVED"}

        url = reverse("template-status")

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "APPROVED")
        self.update_usecase.execute.assert_called_once_with(payload)

    def test_patch_status_not_found(self):
        self.update_usecase.execute = Mock(side_effect=NotFound("not found"))

        payload = {"version_uuid": str(uuid4()), "status": "APPROVED"}

        url = reverse("template-status")
        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
