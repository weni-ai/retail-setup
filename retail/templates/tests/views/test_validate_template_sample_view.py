"""View tests for ``POST /api/v3/templates/<uuid>/sample/`` (T018 / US1 + SC-008).

Covers the HTTP boundary for the happy path (HTTP 200 UTILITY +
MARKETING), the auth gates (401 / 403 / 404), serializer-level
validation (400), and the FR-002b ``project_uuid_mismatch`` defense
with the WARNING-level audit-log line emitted by the view per T016.
"""

from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
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
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleResult,
)


User = get_user_model()

USECASE_PATCH_PATH = "retail.templates.views.ValidateTemplateSampleUseCase"
VIEW_LOGGER = "retail.templates.views"


@with_test_settings
class ValidateTemplateSampleViewTest(BaseTestMixin, APITestCase):
    """HTTP boundary tests for the ``sample`` action on TemplateViewSet."""

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_user(
            username="testuser", password="testpass", email="test@example.com"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(uuid=uuid4(), name="Project")
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="agent",
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
            name="test_template",
            integrated_agent=self.integrated_agent,
            parent=self.parent,
            metadata={"category": "UTILITY", "body": "Original"},
        )
        self.version = Version.objects.create(
            template=self.template,
            template_name="weni_test_template_initial",
            integrations_app_uuid=uuid4(),
            project=self.project,
            status="APPROVED",
        )
        self.template.current_version = self.version
        self.template.save(update_fields=["current_version"])

    def _project_headers_and_params(self):
        return (
            {"HTTP_PROJECT_UUID": str(self.project.uuid)},
            {"user_email": self.user.email},
        )

    def _sample_url(self, template_uuid=None):
        target_uuid = str(template_uuid or self.template.uuid)
        _, params = self._project_headers_and_params()
        return (
            reverse("template-sample", args=[target_uuid])
            + "?"
            + "&".join(f"{k}={v}" for k, v in params.items())
        )

    def _default_payload(self, project_uuid=None):
        return {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(project_uuid or self.project.uuid),
        }

    def _set_up_authorized_request(self):
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )

    def test_utility_classification_returns_200_with_wrapper_fields(self):
        self._set_up_authorized_request()

        result = ValidateTemplateSampleResult(
            category="UTILITY",
            template_updated=True,
            template=self.template,
            meta_sample_response={"success": True, "category": "UTILITY"},
        )

        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            mock_use_case_class.return_value.execute.return_value = result
            headers, _ = self._project_headers_and_params()
            response = self.client.post(
                self._sample_url(),
                self._default_payload(),
                format="json",
                **headers,
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(response.data.keys()),
            {"category", "template_updated", "template", "meta_sample_response"},
        )
        self.assertEqual(response.data["category"], "UTILITY")
        self.assertTrue(response.data["template_updated"])

    def test_marketing_classification_returns_200_with_template_unchanged(self):
        self._set_up_authorized_request()

        result = ValidateTemplateSampleResult(
            category="MARKETING",
            template_updated=False,
            template=self.template,
            meta_sample_response={"success": True, "category": "MARKETING"},
        )

        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            mock_use_case_class.return_value.execute.return_value = result
            headers, _ = self._project_headers_and_params()
            response = self.client.post(
                self._sample_url(),
                self._default_payload(),
                format="json",
                **headers,
            )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["template_updated"])
        self.assertEqual(response.data["category"], "MARKETING")

    def test_unauthenticated_request_returns_403(self):
        client = APIClient()
        response = client.post(
            self._sample_url(), self._default_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_project_uuid_header_returns_403(self):
        self.setup_internal_user_permissions(self.user)
        response = self.client.post(
            self._sample_url(),
            self._default_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_serializer_validation_error_returns_400(self):
        self._set_up_authorized_request()
        headers, _ = self._project_headers_and_params()
        payload = self._default_payload()
        payload["template_body"] = "x" * 1025

        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            response = self.client.post(
                self._sample_url(),
                payload,
                format="json",
                **headers,
            )
            mock_use_case_class.return_value.execute.assert_not_called()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("template_body", response.data)

    def test_project_uuid_mismatch_returns_400_and_emits_warning_log(self):
        self._set_up_authorized_request()
        headers, _ = self._project_headers_and_params()
        payload = self._default_payload(project_uuid=str(uuid4()))

        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            with self.assertLogs(VIEW_LOGGER, level="WARNING") as log_ctx:
                response = self.client.post(
                    self._sample_url(),
                    payload,
                    format="json",
                    **headers,
                )
            mock_use_case_class.return_value.execute.assert_not_called()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project_uuid", response.data)
        any_mismatch_log = any(
            "[TemplateSampleValidation] project_uuid_mismatch:" in record.getMessage()
            for record in log_ctx.records
        )
        self.assertTrue(any_mismatch_log)

    def test_template_uuid_not_found_returns_404(self):
        self._set_up_authorized_request()
        headers, _ = self._project_headers_and_params()
        non_existent_uuid = uuid4()

        from rest_framework.exceptions import NotFound

        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            mock_use_case_class.return_value.execute.side_effect = NotFound(
                f"Template not found: {non_existent_uuid}"
            )
            response = self.client.post(
                self._sample_url(template_uuid=non_existent_uuid),
                self._default_payload(),
                format="json",
                **headers,
            )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_view_passes_request_context_to_serializer(self):
        """Pin that the view constructs the serializer with the request context.

        Re-uses the project_uuid_mismatch defense as a structural witness:
        the check only fires when the serializer can read
        ``request.headers["Project-Uuid"]`` from its context, so if the
        view forgot to pass ``context={"request": request}`` the mismatch
        would never be detected and the use case would be invoked with a
        cross-tenant body. This test pins the wiring by asserting the
        mismatch IS detected.
        """
        self._set_up_authorized_request()
        headers, _ = self._project_headers_and_params()
        payload = self._default_payload(project_uuid=str(uuid4()))

        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            response = self.client.post(
                self._sample_url(),
                payload,
                format="json",
                **headers,
            )
            mock_use_case_class.return_value.execute.assert_not_called()

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
