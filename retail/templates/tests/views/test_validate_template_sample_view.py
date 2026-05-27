"""View tests for ``POST /api/v3/templates/<uuid>/sample/``.

Anchor: FR-002b / FR-005a / SC-008 (see
``specs/004-template-sample-validation/spec.md``).
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
from retail.templates.exceptions import (
    MetaInvalidResponseError,
    MetaSampleUnavailableError,
    NotDirectSendEligibleError,
    WabaNotConfiguredError,
)
from retail.templates.models import Template, Version
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleResult,
)


User = get_user_model()

USECASE_PATCH_PATH = "retail.templates.views.ValidateTemplateSampleUseCase"
INTEGRATIONS_SERVICE_PATCH_PATH = (
    "retail.services.integrations.service.IntegrationsService"
)
VIEW_LOGGER = "retail.templates.views"


@with_test_settings
@patch(INTEGRATIONS_SERVICE_PATCH_PATH)
class ValidateTemplateSampleViewTest(BaseTestMixin, APITestCase):
    """HTTP boundary tests for the ``sample`` action on TemplateViewSet.

    The class-level ``IntegrationsService`` patch ensures the use-case
    default-instantiation never reaches the live integrations engine
    even when individual tests bypass the ``ValidateTemplateSampleUseCase``
    mock (Phase 3b / T037). The patched mock is passed as the last
    positional argument to every test method; tests that exercise the
    happy path can configure it via
    ``mock_integrations_service.return_value.get_channel_app.return_value = {...}``.
    """

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

    def test_utility_classification_returns_200_with_wrapper_fields(
        self, mock_integrations_service
    ):
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

    def test_marketing_classification_returns_200_with_template_unchanged(
        self, mock_integrations_service
    ):
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

    def test_unauthenticated_request_returns_403(self, mock_integrations_service):
        client = APIClient()
        response = client.post(
            self._sample_url(), self._default_payload(), format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_project_uuid_header_returns_403(self, mock_integrations_service):
        self.setup_internal_user_permissions(self.user)
        response = self.client.post(
            self._sample_url(),
            self._default_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_serializer_validation_error_returns_400(self, mock_integrations_service):
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

    def test_project_uuid_mismatch_returns_400_and_emits_warning_log(
        self, mock_integrations_service
    ):
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

    def test_template_uuid_not_found_returns_404(self, mock_integrations_service):
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

    def test_view_passes_request_context_to_serializer(self, mock_integrations_service):
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


META_SERVICE_PATCH_PATH = "retail.services.meta.service.MetaService"
USECASE_LOGGER = "retail.templates.usecases.validate_template_sample"
_BUG_REPORT_WABA_ID = "100200300400500"


@with_test_settings
@patch(META_SERVICE_PATCH_PATH)
@patch(INTEGRATIONS_SERVICE_PATCH_PATH)
class ValidateTemplateSampleViewExtendedShape1bIntegrationTest(
    BaseTestMixin, APITestCase
):
    """End-to-end no-button-with-header wire body regression. Anchor: FR-004."""

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_user(
            username="testuser-3c", password="testpass", email="test-3c@example.com"
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(uuid=uuid4(), name="Project")
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="agent-3c",
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
            name="order_received",
            integrated_agent=self.integrated_agent,
            parent=self.parent,
            metadata={"category": "UTILITY", "body": "Original {{1}}"},
        )
        self.version = Version.objects.create(
            template=self.template,
            template_name="weni_order_received_initial",
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

    def _bug_report_payload(self) -> dict:
        return {
            "template_body": (
                "Olá {{1}}!\n\nRecebemos seu pedido {{2}}. "
                "Em breve nossa equipe entrará em contato."
            ),
            "template_header": "Pedido recebido",
            "template_body_params": ["John", "nº 12345"],
            "template_button": [],
            "app_uuid": str(uuid4()),
            "project_uuid": str(self.project.uuid),
            "language": "pt_BR",
        }

    def _post_bug_report(self, payload: dict):
        return self.client.post(
            reverse("template-sample", args=[str(self.template.uuid)])
            + f"?user_email={self.user.email}",
            payload,
            format="json",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

    def test_bug_report_payload_emits_extended_shape_1b_and_updates_template(
        self, mock_integrations_service, mock_meta_service
    ):
        mock_integrations_service.return_value.get_channel_app.return_value = {
            "config": {"waba": {"id": _BUG_REPORT_WABA_ID}}
        }
        mock_meta_service.return_value.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }

        baseline_version_count = self.template.versions.count()
        payload = self._bug_report_payload()

        with self.assertLogs(USECASE_LOGGER, level="INFO") as log_ctx:
            response = self._post_bug_report(payload)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["category"], "UTILITY")
        self.assertTrue(response.data["template_updated"])
        self.assertEqual(
            response.data["meta_sample_response"],
            {"success": True, "category": "UTILITY"},
        )

        mock_meta_service.return_value.submit_template_sample.assert_called_once()
        call_args = mock_meta_service.return_value.submit_template_sample.call_args
        waba_arg, sample_body = call_args.args
        self.assertEqual(waba_arg, _BUG_REPORT_WABA_ID)
        self.assertEqual(set(sample_body.keys()), {"type", "header", "text"})
        self.assertEqual(sample_body["type"], "text")
        self.assertEqual(
            sample_body["header"], {"type": "text", "text": "Pedido recebido"}
        )
        self.assertEqual(
            sample_body["text"]["body"],
            "Olá John!\n\nRecebemos seu pedido nº 12345. "
            "Em breve nossa equipe entrará em contato.",
        )

        self.template.refresh_from_db()
        self.assertEqual(self.template.metadata["header"]["text"], "Pedido recebido")
        self.assertIn("{{1}}", self.template.metadata["body"])
        self.assertIn("{{2}}", self.template.metadata["body"])
        self.assertEqual(self.template.versions.count(), baseline_version_count + 1)
        new_version = self.template.current_version
        self.assertNotEqual(new_version.uuid, self.version.uuid)
        self.assertEqual(new_version.status, "APPROVED")

        events = [self._event_of(record) for record in log_ctx.records]
        self.assertIn("received", events)
        self.assertIn("meta_sample_submitted", events)

        received_record = next(
            r for r in log_ctx.records if "received:" in r.getMessage()
        )
        received_message = received_record.getMessage()
        self.assertIn("template_header_present=True", received_message)
        self.assertIn("template_footer_present=False", received_message)
        self.assertIn("buttons_count=0", received_message)

        submitted_record = next(
            r for r in log_ctx.records if "meta_sample_submitted:" in r.getMessage()
        )
        self.assertIn("sample_type=text", submitted_record.getMessage())

    @staticmethod
    def _event_of(record) -> str:
        message = record.getMessage()
        prefix, _, _ = message.partition(":")
        return prefix.replace("[TemplateSampleValidation] ", "")


@with_test_settings
@patch(INTEGRATIONS_SERVICE_PATCH_PATH)
class ValidateTemplateSampleViewErrorPathTest(BaseTestMixin, APITestCase):
    """View-level domain-exception HTTP boundary. Anchor: FR-007 / FR-007b."""

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_user(
            username="testuser-error-path",
            password="testpass",
            email="error-path@example.com",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(uuid=uuid4(), name="Project")
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="agent-error-path",
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
            name="error_path_template",
            integrated_agent=self.integrated_agent,
            parent=self.parent,
            metadata={"category": "UTILITY", "body": "Original"},
        )

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

    def _post_with_use_case_raising(self, exception_instance):
        with patch(USECASE_PATCH_PATH) as mock_use_case_class:
            mock_use_case_class.return_value.execute.side_effect = exception_instance
            return self.client.post(
                self._sample_url(),
                self._default_payload(),
                format="json",
                HTTP_PROJECT_UUID=str(self.project.uuid),
            )

    def test_not_direct_send_eligible_translates_to_400_without_meta_response(
        self, mock_integrations_service
    ):
        response = self._post_with_use_case_raising(
            NotDirectSendEligibleError("not eligible")
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"], "Template is not Direct Send-eligible"
        )
        self.assertEqual(response.data["error_code"], "not_direct_send_eligible")
        self.assertNotIn("meta_response", response.data)

    def test_waba_not_configured_translates_to_400_without_meta_response(
        self, mock_integrations_service
    ):
        response = self._post_with_use_case_raising(
            WabaNotConfiguredError("waba missing")
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            response.data["detail"], "WABA not configured for this project"
        )
        self.assertEqual(response.data["error_code"], "waba_not_configured")
        self.assertNotIn("meta_response", response.data)

    def test_meta_sample_unavailable_with_envelope_includes_meta_response(
        self, mock_integrations_service
    ):
        upstream_envelope = {"error": {"message": "rate limited", "code": 130472}}
        response = self._post_with_use_case_raising(
            MetaSampleUnavailableError(
                "Meta unavailable",
                status_code=429,
                meta_response=upstream_envelope,
            )
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["detail"], "Meta sample submission failed")
        self.assertEqual(response.data["error_code"], "meta_unavailable")
        self.assertEqual(response.data["meta_response"], upstream_envelope)

    def test_meta_sample_unavailable_without_envelope_omits_meta_response(
        self, mock_integrations_service
    ):
        response = self._post_with_use_case_raising(
            MetaSampleUnavailableError(
                "Meta unavailable",
                status_code=None,
                meta_response=None,
            )
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["detail"], "Meta sample submission failed")
        self.assertEqual(response.data["error_code"], "meta_unavailable")
        self.assertNotIn("meta_response", response.data)

    def test_meta_invalid_response_includes_raw_meta_body(
        self, mock_integrations_service
    ):
        raw_meta_body = {"success": True}
        response = self._post_with_use_case_raising(
            MetaInvalidResponseError("no category", meta_response=raw_meta_body)
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data["detail"], "Meta did not return a category")
        self.assertEqual(response.data["error_code"], "meta_invalid_response")
        self.assertEqual(response.data["meta_response"], raw_meta_body)


META_SERVICE_PATCH_PATH_SC008 = "retail.services.meta.service.MetaService"


@with_test_settings
@patch(META_SERVICE_PATCH_PATH_SC008)
@patch(INTEGRATIONS_SERVICE_PATCH_PATH)
class ValidateTemplateSampleViewCrossTenantIsolationTest(BaseTestMixin, APITestCase):
    """Cross-tenant isolation structural guarantee. Anchor: FR-002b / SC-008."""

    def setUp(self):
        super().setUp()

        self.user = User.objects.create_user(
            username="testuser-sc008",
            password="testpass",
            email="sc008@example.com",
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

        self.project = Project.objects.create(uuid=uuid4(), name="Project")
        self.agent = Agent.objects.create(
            uuid=uuid4(),
            name="Agent",
            slug="agent-sc008",
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
            name="sc008_template",
            integrated_agent=self.integrated_agent,
            parent=self.parent,
            metadata={"category": "UTILITY", "body": "Original SC008"},
        )

    def _sample_url(self):
        return (
            reverse("template-sample", args=[str(self.template.uuid)])
            + f"?user_email={self.user.email}"
        )

    def _default_payload(self, project_uuid):
        return {
            "template_body": "Updated body",
            "app_uuid": str(uuid4()),
            "project_uuid": str(project_uuid),
        }

    def _snapshot_template_state(self) -> dict:
        self.template.refresh_from_db()
        return {
            "metadata": dict(self.template.metadata or {}),
            "current_version_id": self.template.current_version_id,
        }

    def test_project_uuid_mismatch_blocks_request_and_emits_audit_log(
        self, mock_integrations_service, mock_meta_service
    ):
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.CONTRIBUTOR_PERMISSIONS,
        )
        other_project_uuid = uuid4()
        pre_snapshot = self._snapshot_template_state()

        with self.assertLogs(VIEW_LOGGER, level="WARNING") as log_ctx:
            response = self.client.post(
                self._sample_url(),
                self._default_payload(project_uuid=other_project_uuid),
                format="json",
                HTTP_PROJECT_UUID=str(self.project.uuid),
            )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("project_uuid", response.data)

        mock_meta_service.return_value.submit_template_sample.assert_not_called()
        mock_integrations_service.return_value.get_channel_app.assert_not_called()

        self.assertEqual(self._snapshot_template_state(), pre_snapshot)

        any_mismatch_log = any(
            "[TemplateSampleValidation] project_uuid_mismatch:" in record.getMessage()
            for record in log_ctx.records
        )
        self.assertTrue(any_mismatch_log)

    def test_unauthenticated_request_is_rejected_before_use_case(
        self, mock_integrations_service, mock_meta_service
    ):
        anonymous_client = APIClient()
        response = anonymous_client.post(
            self._sample_url(),
            self._default_payload(project_uuid=self.project.uuid),
            format="json",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_meta_service.return_value.submit_template_sample.assert_not_called()
        mock_integrations_service.return_value.get_channel_app.assert_not_called()

    def test_authorized_user_for_wrong_project_is_rejected_by_has_project_permission(
        self, mock_integrations_service, mock_meta_service
    ):
        self.setup_internal_user_permissions(self.user)
        self.setup_connect_service_mock(
            status_code=200,
            permissions=ConnectServicePermissionScenarios.NO_PERMISSIONS,
        )

        response = self.client.post(
            self._sample_url(),
            self._default_payload(project_uuid=self.project.uuid),
            format="json",
            HTTP_PROJECT_UUID=str(self.project.uuid),
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        mock_meta_service.return_value.submit_template_sample.assert_not_called()
        mock_integrations_service.return_value.get_channel_app.assert_not_called()
