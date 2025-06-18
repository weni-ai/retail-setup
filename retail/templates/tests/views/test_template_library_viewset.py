from unittest.mock import patch, MagicMock

from uuid import uuid4

from django.urls import reverse
from django.contrib.auth.models import User, Permission
from rest_framework import status
from rest_framework.test import APITestCase

from retail.templates.models import Template, Version
from retail.agents.push.models import PreApprovedTemplate, Agent
from retail.projects.models import Project


class TestTemplateLibraryViewSet(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="testuser", password="testpass123"
        )

        permission = Permission.objects.get_or_create(
            codename="can_communicate_internally",
            defaults={
                "name": "Can communicate internally",
                "content_type_id": 1,
            },
        )[0]
        self.user.user_permissions.add(permission)

        # Authenticate the user
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(
            uuid=uuid4(),
            name="Test Project",
        )

        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Test Agent",
            project=self.project,
        )

        self.parent = PreApprovedTemplate.objects.create(
            uuid=uuid4(),
            name="test_parent",
            display_name="Test Parent Template",
            start_condition="test condition",
            agent=self.agent,
        )

        self.template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
        )

        self.version = Version.objects.create(
            template=self.template,
            template_name="test_template",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )

        self.template.current_version = self.version
        self.template.save()

        self.app_uuid = str(uuid4())
        self.project_uuid = str(self.project.uuid)
        self.update_library_usecase = MagicMock()
        self.update_library_usecase_patch = patch(
            "retail.templates.views.UpdateLibraryTemplateUseCase",
            return_value=self.update_library_usecase,
        )
        self.update_library_usecase_patch.start()
        self.addCleanup(self.update_library_usecase_patch.stop)

    def test_partial_update_success(self):
        self.update_library_usecase.execute.return_value = self.template

        payload = {
            "library_template_button_inputs": [
                {
                    "type": "URL",
                    "url": {
                        "base_url": "https://example.com",
                        "url_suffix_example": "/path",
                    },
                }
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}"

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "test_template")
        self.assertEqual(response.data["status"], "APPROVED")

        # Verify the use case was called with correct data
        self.update_library_usecase.execute.assert_called_once()
        call_args = self.update_library_usecase.execute.call_args[0][0]
        self.assertEqual(call_args["template_uuid"], str(self.template.uuid))
        self.assertEqual(call_args["app_uuid"], self.app_uuid)
        self.assertEqual(call_args["project_uuid"], self.project_uuid)
        self.assertEqual(
            call_args["library_template_button_inputs"],
            payload["library_template_button_inputs"],
        )

    def test_partial_update_missing_app_uuid(self):
        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?project_uuid={self.project_uuid}"

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("app_uuid and project_uuid are required", str(response.data))
        self.update_library_usecase.execute.assert_not_called()

    def test_partial_update_missing_project_uuid(self):
        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}"

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("app_uuid and project_uuid are required", str(response.data))
        self.update_library_usecase.execute.assert_not_called()

    def test_partial_update_missing_both_query_params(self):
        payload = {
            "library_template_button_inputs": [
                {"type": "URL", "url": {"base_url": "https://example.com"}}
            ]
        }

        url = reverse("template-library-detail", args=[str(self.template.uuid)])

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("app_uuid and project_uuid are required", str(response.data))
        self.update_library_usecase.execute.assert_not_called()

    def test_partial_update_empty_payload(self):
        self.update_library_usecase.execute.return_value = self.template

        payload = {}

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}"

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_partial_update_invalid_serializer_data(self):
        payload = {"library_template_button_inputs": "invalid_data"}

        url = reverse("template-library-detail", args=[str(self.template.uuid)])
        url += f"?app_uuid={self.app_uuid}&project_uuid={self.project_uuid}"

        response = self.client.patch(url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.update_library_usecase.execute.assert_not_called()
