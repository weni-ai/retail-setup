"""View tests for ``POST /api/v3/templates/<uuid>/sample/`` (T018 / US1 + SC-008).

Covers the HTTP boundary for the happy path (HTTP 200 UTILITY +
MARKETING), the auth gates (401 / 403 / 404), serializer-level
validation (400), and the FR-002b ``project_uuid_mismatch`` defense
with the WARNING-level audit-log line emitted by the view per T016.

Phase 3b (T037): the WABA-id resolution path was switched to call
``IntegrationsService.get_channel_app("wpp-cloud", dto.app_uuid)`` per
FR-005a / A2. A class-level patch guards the
``IntegrationsService`` symbol the use-case ``__init__`` resolves so
that even if a future refactor drops the per-test
``ValidateTemplateSampleUseCase`` mock, the integrations engine is
never reached from a unit test (defense-in-depth — no live network).
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

    def test_missing_project_uuid_header_returns_403(
        self, mock_integrations_service
    ):
        self.setup_internal_user_permissions(self.user)
        response = self.client.post(
            self._sample_url(),
            self._default_payload(),
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_serializer_validation_error_returns_400(
        self, mock_integrations_service
    ):
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

    def test_view_passes_request_context_to_serializer(
        self, mock_integrations_service
    ):
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
    """T041 / Phase 3c — end-to-end integration test for the bug-report case.

    Unlike the upstream ``ValidateTemplateSampleViewTest`` (which patches
    the entire ``ValidateTemplateSampleUseCase`` to assert on the HTTP
    boundary in isolation), this class lets the real use case execute
    against patched ``IntegrationsService`` and ``MetaService`` so the
    extended Shape 1b wire body is observed at the actual ``MetaService``
    boundary (the only mock surface). This pins spec AS4 / FR-004
    (post-clarification) end-to-end: the bug case reported 2026-05-26
    (``{template_body, template_header: "Pedido recebido", template_button:
    []}``) MUST emit ``{"type": "text", "header": {"type": "text", "text":
    "Pedido recebido"}, "text": {"body": ...}}`` and update local state.
    """

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
        self.assertEqual(
            self.template.versions.count(), baseline_version_count + 1
        )
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
            r
            for r in log_ctx.records
            if "meta_sample_submitted:" in r.getMessage()
        )
        self.assertIn("sample_type=text", submitted_record.getMessage())

    @staticmethod
    def _event_of(record) -> str:
        message = record.getMessage()
        prefix, _, _ = message.partition(":")
        return prefix.replace("[TemplateSampleValidation] ", "")
