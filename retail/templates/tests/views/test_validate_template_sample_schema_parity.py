"""Schema-parity tests for the sample endpoint. Anchor: FR-014 / SC-005."""

from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient, APITestCase
from rest_framework import status

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent, PreApprovedTemplate
from retail.internal.test_mixins import (
    BaseTestMixin,
    ConnectServicePermissionScenarios,
    with_test_settings,
)
from retail.projects.models import Project
from retail.templates.models import Template, Version
from retail.templates.serializers import (
    ReadTemplateSerializer,
    UpdateTemplateContentSerializer,
    ValidateTemplateSampleSerializer,
)
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleResult,
)


User = get_user_model()

USECASE_PATCH_PATH = "retail.templates.views.ValidateTemplateSampleUseCase"
INTEGRATIONS_SERVICE_PATCH_PATH = (
    "retail.services.integrations.service.IntegrationsService"
)

_EXPECTED_WRAPPER_KEYS = {
    "category",
    "template_updated",
    "template",
    "meta_sample_response",
}


class ValidateTemplateSampleRequestSchemaParityTest(TestCase):
    """Request field set parity with the legacy PATCH serializer."""

    def test_field_set_matches_update_template_content_serializer(self):
        legacy_fields = set(UpdateTemplateContentSerializer().fields.keys())
        sample_fields = set(ValidateTemplateSampleSerializer().fields.keys())

        self.assertEqual(sample_fields, legacy_fields)

    def test_sample_serializer_inherits_from_update_template_content_serializer(self):
        """Inheritance link is the source of parity."""
        self.assertTrue(
            issubclass(
                ValidateTemplateSampleSerializer, UpdateTemplateContentSerializer
            )
        )


@with_test_settings
@patch(INTEGRATIONS_SERVICE_PATCH_PATH)
class ValidateTemplateSampleResponseSchemaParityTest(BaseTestMixin, APITestCase):
    """HTTP 200 ``template`` equals ``ReadTemplateSerializer``. Anchor: FR-007 / SC-005."""

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_user(
            username="testuser-schema-parity",
            password="testpass",
            email="schema-parity@example.com",
        )
        self.client = APIClient()

        self.project = Project.objects.create(uuid=uuid4(), name="Project")

        self.start_retail_auth(
            project_uuid=self.project.uuid, user_email=self.user.email
        )
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="agent-schema-parity",
            description="desc",
            project=self.project,
        )
        self.parent = PreApprovedTemplate.objects.create(
            agent=self.agent,
            uuid=uuid4(),
            name="parent",
            display_name="Parent",
            content="content",
            is_valid=True,
            start_condition="always",
            metadata={},
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            uuid=uuid4(),
            agent=self.agent,
            project=self.project,
            is_active=True,
            config={"direct_send": True},
        )
        self.template = Template.objects.create(
            uuid=uuid4(),
            name="schema_parity_template",
            integrated_agent=self.integrated_agent,
            parent=self.parent,
            metadata={
                "category": "UTILITY",
                "body": "Olá {{1}}",
                "header": {"header_type": "TEXT", "text": "Pedido entregue"},
                "footer": "Equipe Loja XYZ",
                "language": "pt_BR",
            },
        )
        self.version = Version.objects.create(
            template=self.template,
            template_name="weni_schema_parity_initial",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        self.template.current_version = self.version
        self.template.save(update_fields=["current_version"])

        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

    def _sample_url(self):
        return (
            reverse("template-sample", args=[str(self.template.uuid)])
            + f"?user_email={self.user.email}"
        )

    def _default_payload(self):
        return {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
        }

    def _post_with_use_case_returning(self, result):
        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            mock_use_case_class.return_value.execute.return_value = result
            return self.client.post(
                self._sample_url(),
                self._default_payload(),
                format="json",
                HTTP_PROJECT_UUID=str(self.project.uuid),
            )

    def test_response_wrapper_has_exactly_four_top_level_keys(
        self, mock_integrations_service
    ):
        meta_sample_response = {"success": True, "category": "UTILITY"}
        result = ValidateTemplateSampleResult(
            category="UTILITY",
            template_updated=True,
            template=self.template,
            meta_sample_response=meta_sample_response,
        )

        response = self._post_with_use_case_returning(result)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(set(response.data.keys()), _EXPECTED_WRAPPER_KEYS)

    def test_response_template_field_equals_read_template_serializer(
        self, mock_integrations_service
    ):
        meta_sample_response = {"success": True, "category": "UTILITY"}
        result = ValidateTemplateSampleResult(
            category="UTILITY",
            template_updated=True,
            template=self.template,
            meta_sample_response=meta_sample_response,
        )

        response = self._post_with_use_case_returning(result)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.template.refresh_from_db()
        expected_template_payload = ReadTemplateSerializer(self.template).data
        self.assertEqual(response.data["template"], expected_template_payload)

    def test_response_meta_sample_response_is_forwarded_verbatim(
        self, mock_integrations_service
    ):
        meta_sample_response = {
            "success": True,
            "category": "UTILITY",
            "id": "1234567890",
        }
        result = ValidateTemplateSampleResult(
            category="UTILITY",
            template_updated=True,
            template=self.template,
            meta_sample_response=meta_sample_response,
        )

        response = self._post_with_use_case_returning(result)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["meta_sample_response"], meta_sample_response)
