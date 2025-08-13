from uuid import uuid4
from unittest.mock import patch, MagicMock

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from rest_framework.test import APITestCase, APIClient
from rest_framework import status

from retail.agents.models import PreApprovedTemplate, Agent, IntegratedAgent
from retail.templates.models import Template
from retail.projects.models import Project

User = get_user_model()

CONNECT_SERVICE_PATH = "retail.internal.permissions.ConnectService"


class TemplateViewSetStrategyIntegrationTest(APITestCase):
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
    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch("retail.templates.handlers.TemplateMetadataHandler")
    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateNormalTemplateStrategy.update_template"
    )
    def test_normal_template_update_uses_normal_strategy(
        self,
        mock_update_method,
        mock_metadata_handler_class,
        mock_s3_service,
        mock_connect_service,
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="normal_template",
            parent=self.parent,
            metadata={"category": "UTILITY", "body": "Original body"},
        )

        mock_update_method.return_value = template

        payload = {
            "template_body": "Updated body for normal template",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
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

        mock_update_method.assert_called_once()
        call_args = mock_update_method.call_args
        self.assertEqual(call_args[0][0], template)  # First argument is the template
        self.assertEqual(
            call_args[0][1]["template_body"], "Updated body for normal template"
        )

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch("retail.templates.handlers.TemplateMetadataHandler")
    @patch("retail.templates.strategies.update_template_strategies.RuleGenerator")
    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateCustomTemplateStrategy.update_template"
    )
    def test_custom_template_update_uses_custom_strategy(
        self,
        mock_update_method,
        mock_rule_generator_class,
        mock_metadata_handler_class,
        mock_s3_service,
        mock_connect_service,
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="custom_template",
            integrated_agent=self.integrated_agent,
            metadata={"category": "UTILITY", "body": "Original body"},
        )

        mock_update_method.return_value = template

        payload = {
            "template_body": "Updated body for custom template",
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

        template_uuid = str(template.uuid)
        headers, params = self._get_project_headers_and_params()
        url = (
            reverse("template-detail", args=[template_uuid])
            + "?"
            + "&".join([f"{k}={v}" for k, v in params.items()])
        )

        response = self.client.patch(url, payload, format="json", **headers)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        mock_update_method.assert_called_once()
        call_args = mock_update_method.call_args
        self.assertEqual(call_args[0][0], template)  # First argument is the template
        self.assertEqual(
            call_args[0][1]["template_body"], "Updated body for custom template"
        )
        self.assertEqual(len(call_args[0][1]["parameters"]), 2)
        self.assertEqual(call_args[0][1]["parameters"][0]["name"], "start_condition")

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch("retail.templates.handlers.TemplateMetadataHandler")
    @patch("retail.templates.strategies.update_template_strategies.RuleGenerator")
    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateTemplateStrategyFactory.create_strategy"
    )
    def test_strategy_factory_is_called_correctly(
        self,
        mock_create_strategy,
        mock_rule_generator_class,
        mock_metadata_handler_class,
        mock_s3_service,
        mock_connect_service,
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="test_template",
            parent=self.parent,
            metadata={"category": "UTILITY", "body": "Original body"},
        )

        mock_strategy = MagicMock()
        mock_strategy.update_template.return_value = template
        mock_create_strategy.return_value = mock_strategy

        payload = {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
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

        mock_create_strategy.assert_called_once()
        call_args = mock_create_strategy.call_args
        self.assertEqual(call_args[1]["template"], template)
        self.assertIn("template_adapter", call_args[1])
        self.assertIn("rule_generator", call_args[1])

        mock_strategy.update_template.assert_called_once()

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch("retail.templates.handlers.TemplateMetadataHandler")
    @patch(
        "retail.templates.strategies.update_template_strategies.UpdateNormalTemplateStrategy.update_template"
    )
    def test_normal_template_ignores_parameters(
        self,
        mock_update_method,
        mock_metadata_handler_class,
        mock_s3_service,
        mock_connect_service,
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="normal_template",
            parent=self.parent,
            metadata={"category": "UTILITY", "body": "Original body"},
        )

        mock_update_method.return_value = template

        payload = {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "parameters": [{"name": "should_be_ignored", "value": "ignored"}],
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
        mock_update_method.assert_called_once()

    @patch(CONNECT_SERVICE_PATH)
    @patch("retail.templates.handlers.template_metadata.S3Service")
    @patch("retail.templates.handlers.TemplateMetadataHandler")
    @patch("retail.templates.strategies.update_template_strategies.RuleGenerator")
    def test_custom_template_with_parameters_is_allowed(
        self,
        mock_rule_generator_class,
        mock_metadata_handler_class,
        mock_s3_service,
        mock_connect_service,
    ):
        self._add_internal_permission_to_user()

        mock_connect_service.return_value.get_user_permissions.return_value = (
            200,
            {"project_authorization": 2},  # contributor level
        )

        template = Template.objects.create(
            uuid=uuid4(),
            name="custom_template",
            integrated_agent=self.integrated_agent,
            metadata={"category": "UTILITY", "body": "Original body"},
        )

        with patch(
            "retail.templates.strategies.update_template_strategies.UpdateCustomTemplateStrategy.update_template"
        ) as mock_update:
            mock_update.return_value = template

            payload = {
                "template_body": "Updated body",
                "app_uuid": str(uuid4()),
                "project_uuid": str(self.project.uuid),
                "parameters": [
                    {"name": "start_condition", "value": "user.is_active == true"},
                ],
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
            mock_update.assert_called_once()
