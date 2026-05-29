"""Tests for ``ValidateTemplateSampleUseCase``. Anchor: FR-006 / FR-008b."""

import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.clients.exceptions import CustomAPIException
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.projects.models import Project
from retail.templates.exceptions import (
    MetaInvalidResponseError,
    MetaSampleUnavailableError,
    NotDirectSendEligibleError,
    WabaNotConfiguredError,
)
from retail.templates.models import Template, Version
from retail.templates.usecases.update_template_body import (
    UpdateTemplateContentUseCase,
)
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleDTO,
    ValidateTemplateSampleUseCase,
)


USECASE_LOGGER = "retail.templates.usecases.validate_template_sample"
TASK_CREATE_TEMPLATE_PATH = (
    "retail.templates.strategies.update_template_strategies.task_create_template"
)

_DEFAULT_APP_UUID = "22222222-2222-2222-2222-222222222222"
_WABA_ID = "987654321"


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "validate-template-sample-tests",
        }
    },
    USE_S3=False,
    USE_META=False,
    META_API_URL="http://test-meta.local",
    META_SYSTEM_USER_ACCESS_TOKEN="test-token",
)
class _UseCaseTestBase(TestCase):
    """Shared fixtures: Direct Send-eligible Template + mocked integrations."""

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(uuid=uuid4(), name="Test Project")
        self.agent = Agent.objects.create(
            project=self.project,
            name="OrderStatus",
            slug="order-status",
            description="desc",
        )
        self.integrated_agent = IntegratedAgent.objects.create(
            agent=self.agent,
            project=self.project,
            uuid=uuid4(),
            config={"direct_send": True},
        )
        self.template = Template.objects.create(
            uuid=uuid4(),
            name="order_invoiced",
            integrated_agent=self.integrated_agent,
            metadata={
                "category": "UTILITY",
                "body": "Original body {{1}}",
                "language": "pt_BR",
            },
        )

        self.meta_service = MagicMock()
        self.metadata_handler = MagicMock()
        self.metadata_handler._upload_header_image.return_value = (
            "https://bucket.s3.amazonaws.com/uploaded.png"
        )
        self.integrations_service = MagicMock(spec=IntegrationsServiceInterface)
        self.integrations_service.get_channel_app.return_value = {
            "config": {"waba": {"id": _WABA_ID}}
        }
        self.use_case = ValidateTemplateSampleUseCase(
            meta_service=self.meta_service,
            metadata_handler=self.metadata_handler,
            integrations_service=self.integrations_service,
        )

    def _build_dto(self, **overrides) -> ValidateTemplateSampleDTO:
        defaults = dict(
            template_uuid=str(self.template.uuid),
            template_body="Updated body {{1}}",
            template_header=None,
            template_footer=None,
            template_button=None,
            template_body_params=["João"],
            app_uuid=_DEFAULT_APP_UUID,
            project_uuid=str(self.project.uuid),
            parameters=None,
            language="pt_BR",
        )
        defaults.update(overrides)
        return ValidateTemplateSampleDTO(**defaults)


class HappyPathUtilityBodyOnlyTest(_UseCaseTestBase):
    """T017 (a) — body-only UTILITY edit advances current_version with APPROVED."""

    def test_utility_classification_writes_approved_version_and_advances_pointer(self):
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto()

        with self.assertLogs(USECASE_LOGGER, level="INFO") as log_ctx:
            result = self.use_case.execute(dto)

        self.template.refresh_from_db()
        new_version = self.template.current_version

        self.assertIsNotNone(new_version)
        self.assertEqual(new_version.status, "APPROVED")
        self.assertEqual(self.template.metadata["body"], "Updated body {{1}}")
        self.assertTrue(result.template_updated)
        self.assertEqual(result.category, "UTILITY")

        events = [self._event_of(record) for record in log_ctx.records]
        self.assertEqual(
            events,
            [
                "received",
                "meta_sample_submitted",
                "meta_sample_response",
                "template_updated",
            ],
        )
        for record in log_ctx.records:
            self.assertEqual(record.levelno, logging.INFO)

        self.meta_service.submit_template_sample.assert_called_once()
        call_args = self.meta_service.submit_template_sample.call_args
        self.assertEqual(call_args.args[0], _WABA_ID)
        self.assertEqual(call_args.args[1]["type"], "text")

        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )

    def _event_of(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        prefix, _, rest = message.partition(":")
        return prefix.replace("[TemplateSampleValidation] ", "")


class HappyPathUtilityCtaUrlTextHeaderTest(_UseCaseTestBase):
    """T017 (b) — TEXT header + footer + CTA URL button payload."""

    def test_cta_url_payload_persists_canonical_button_metadata(self):
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto(
            template_header="Order status",
            template_footer="Team Shop",
            template_button=[
                {
                    "type": "URL",
                    "text": "Confirm",
                    "url": {
                        "base_url": "https://shop.example.com/confirm",
                        "url_suffix_example": "abc",
                    },
                }
            ],
        )

        result = self.use_case.execute(dto)

        self.template.refresh_from_db()
        self.assertTrue(result.template_updated)
        persisted_buttons = self.template.metadata.get("buttons") or []
        self.assertEqual(len(persisted_buttons), 1)
        self.assertEqual(persisted_buttons[0]["type"], "URL")
        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )


class HappyPathUtilityImageHeaderTest(_UseCaseTestBase):
    """T017 (c) — IMAGE base64 header is uploaded BEFORE the Meta call (A9)."""

    def test_image_base64_header_uploads_to_s3_before_meta_call(self):
        self.metadata_handler._upload_header_image.return_value = (
            "https://bucket.s3.amazonaws.com/uploaded.png"
        )
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto(template_header="data:image/png;base64,abc123")

        self.use_case.execute(dto)

        self.metadata_handler._upload_header_image.assert_called_once()
        self.meta_service.submit_template_sample.assert_called_once()
        wire_body = self.meta_service.submit_template_sample.call_args.args[1]
        self.assertEqual(wire_body["type"], "text")
        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )

    def test_image_base64_header_routes_resolved_url_into_interactive_header(self):
        self.metadata_handler._upload_header_image.return_value = (
            "https://bucket.s3.amazonaws.com/uploaded.png"
        )
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto(
            template_header="data:image/png;base64,abc123",
            template_button=[
                {
                    "type": "URL",
                    "text": "Open",
                    "url": "https://shop.example.com/{{1}}",
                }
            ],
        )

        self.use_case.execute(dto)

        wire_body = self.meta_service.submit_template_sample.call_args.args[1]
        self.assertEqual(
            wire_body["interactive"]["header"]["image"]["link"],
            "https://bucket.s3.amazonaws.com/uploaded.png",
        )
        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )


class HappyPathReplyButtonsTest(_UseCaseTestBase):
    """T017 (d) — reply buttons produce deterministic reply.id values."""

    def test_reply_buttons_get_deterministic_reply_ids(self):
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto(
            template_button=[
                {"type": "QUICK_REPLY", "text": "Yes"},
                {"type": "QUICK_REPLY", "text": "No"},
            ],
        )

        self.use_case.execute(dto)

        wire_body = self.meta_service.submit_template_sample.call_args.args[1]
        buttons = wire_body["interactive"]["action"]["buttons"]
        self.assertEqual(buttons[0]["reply"]["id"], "yes")
        self.assertEqual(buttons[1]["reply"]["id"], "no")
        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )


class NonUtilityNoLocalUpdateTest(_UseCaseTestBase):
    """T017 (e–g) — MARKETING / AUTHENTICATION / arbitrary non-UTILITY are no-ops."""

    NON_UTILITY_CATEGORIES = ["MARKETING", "AUTHENTICATION", "PROMO"]

    def test_non_utility_classifications_skip_local_update(self):
        for category in self.NON_UTILITY_CATEGORIES:
            with self.subTest(category=category):
                self.meta_service.reset_mock()
                self.integrations_service.reset_mock()
                self.integrations_service.get_channel_app.return_value = {
                    "config": {"waba": {"id": _WABA_ID}}
                }
                self.template.refresh_from_db()
                pre_metadata = dict(self.template.metadata)
                pre_current_version = self.template.current_version

                self.meta_service.submit_template_sample.return_value = {
                    "success": True,
                    "category": category,
                }
                dto = self._build_dto()

                with self.assertLogs(USECASE_LOGGER, level="INFO") as log_ctx:
                    result = self.use_case.execute(dto)

                self.template.refresh_from_db()
                self.assertFalse(result.template_updated)
                self.assertEqual(result.category, category)
                self.assertEqual(self.template.metadata, pre_metadata)
                self.assertEqual(self.template.current_version, pre_current_version)

                events = [
                    record.getMessage().partition(":")[0] for record in log_ctx.records
                ]
                self.assertTrue(events[-1].endswith("update_skipped"))
                for record in log_ctx.records:
                    self.assertEqual(record.levelno, logging.INFO)

                self.integrations_service.get_channel_app.assert_called_once_with(
                    "wpp-cloud", dto.app_uuid
                )


class ByteIdenticalResubmissionTest(_UseCaseTestBase):
    """T017 (h) — byte-identical content still calls Meta and writes a new Version."""

    def test_byte_identical_resubmission_creates_new_version(self):
        existing_version = Version.objects.create(
            template=self.template,
            template_name="weni_order_invoiced_existing",
            integrations_app_uuid=_DEFAULT_APP_UUID,
            project=self.project,
            status="APPROVED",
        )
        self.template.current_version = existing_version
        self.template.save(update_fields=["current_version"])

        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        body_matching_metadata = self.template.metadata["body"]
        dto = self._build_dto(template_body=body_matching_metadata)

        result = self.use_case.execute(dto)

        self.meta_service.submit_template_sample.assert_called_once()
        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )
        self.template.refresh_from_db()
        self.assertTrue(result.template_updated)
        self.assertNotEqual(self.template.current_version_id, existing_version.id)
        version_count = Version.objects.filter(template=self.template).count()
        self.assertEqual(version_count, 2)


class BlockedProjectStillProcessesTest(_UseCaseTestBase):
    """T017 (i) — ``Project.is_blocked = True`` does not gate sample validation."""

    def test_blocked_project_still_processes_utility_sample(self):
        self.project.is_blocked = True
        self.project.save(update_fields=["is_blocked"])

        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto()

        result = self.use_case.execute(dto)

        self.template.refresh_from_db()
        self.assertTrue(result.template_updated)
        self.assertEqual(self.template.current_version.status, "APPROVED")
        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )


class DirectSendEligibilityGateTest(_UseCaseTestBase):
    """Eligibility gate runs before the Meta call. Anchor: FR-002a."""

    def test_template_without_integrated_agent_raises_not_eligible(self):
        non_eligible_template = Template.objects.create(
            uuid=uuid4(),
            name="orphan_template",
            metadata={"category": "UTILITY"},
        )
        dto = self._build_dto(template_uuid=str(non_eligible_template.uuid))

        with self.assertRaises(NotDirectSendEligibleError):
            self.use_case.execute(dto)

        self.meta_service.submit_template_sample.assert_not_called()

    def test_direct_send_flag_false_raises_not_eligible(self):
        self.integrated_agent.config = {"direct_send": False}
        self.integrated_agent.save(update_fields=["config"])
        dto = self._build_dto()

        with self.assertRaises(NotDirectSendEligibleError):
            self.use_case.execute(dto)

        self.meta_service.submit_template_sample.assert_not_called()


class ZeroProjectOnboardingQueryRegressionTest(_UseCaseTestBase):
    """WABA resolution never reads ``ProjectOnboarding``. Anchor: FR-005a / SC-008."""

    def test_utility_request_never_reads_project_onboarding(self):
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto()

        with patch(
            "retail.projects.models.ProjectOnboarding.objects",
            new=MagicMock(),
        ) as mock_objects:
            self.use_case.execute(dto)

        mock_objects.filter.assert_not_called()
        mock_objects.get.assert_not_called()
        mock_objects.all.assert_not_called()
        self.integrations_service.get_channel_app.assert_called_once_with(
            "wpp-cloud", dto.app_uuid
        )


class LegacyPatchEndpointMetadataParityTest(_UseCaseTestBase):
    """Sample / legacy PATCH metadata parity. Anchor: SC-005."""

    def _build_legacy_template(self) -> Template:
        return Template.objects.create(
            uuid=uuid4(),
            name="order_invoiced_legacy",
            integrated_agent=self.integrated_agent,
            metadata={
                "category": "UTILITY",
                "body": "Original body {{1}}",
                "language": "pt_BR",
            },
        )

    def _common_payload_fields(self) -> dict:
        return dict(
            template_body="Olá {{1}}, seu pedido {{2}} foi pago.",
            template_header="Pagamento confirmado",
            template_footer="Equipe da loja",
            template_button=[
                {
                    "type": "URL",
                    "text": "Acompanhar pedido",
                    "url": {
                        "base_url": "https://loja.com/track/",
                        "url_suffix_example": "abc123",
                    },
                }
            ],
            template_body_params=["Maria", "12345"],
            app_uuid=_DEFAULT_APP_UUID,
            project_uuid=str(self.project.uuid),
            parameters=None,
            language="pt_BR",
        )

    @patch(TASK_CREATE_TEMPLATE_PATH)
    def test_sample_and_legacy_paths_produce_byte_identical_metadata(
        self, _mock_task_create_template
    ):
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        common = self._common_payload_fields()
        sample_template = self.template
        legacy_template = self._build_legacy_template()

        sample_dto = ValidateTemplateSampleDTO(
            template_uuid=str(sample_template.uuid),
            **common,
        )
        legacy_payload = {
            "template_uuid": str(legacy_template.uuid),
            **common,
        }

        self.use_case.execute(sample_dto)
        UpdateTemplateContentUseCase(rule_generator=MagicMock()).execute(legacy_payload)

        sample_template.refresh_from_db()
        legacy_template.refresh_from_db()

        self.assertEqual(sample_template.metadata, legacy_template.metadata)


class TaskCreateTemplateNotFiredTest(_UseCaseTestBase):
    """Sample endpoint MUST NOT push to Integrations. Anchor: FR-006."""

    @patch(TASK_CREATE_TEMPLATE_PATH)
    def test_utility_classification_does_not_enqueue_create_template_task(
        self, mock_task_create_template
    ):
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto()

        self.use_case.execute(dto)

        mock_task_create_template.delay.assert_not_called()


class _FailurePathAssertionMixin:
    """Shared failure-path assertions. Anchor: FR-005c / FR-006c / FR-008a / FR-008b."""

    def _snapshot_local_state(self, template: Template) -> dict:
        return {
            "metadata": dict(template.metadata or {}),
            "current_version_id": template.current_version_id,
            "current_version_status": (
                template.current_version.status if template.current_version else None
            ),
        }

    def _assert_local_state_unchanged(
        self, template: Template, pre_snapshot: dict
    ) -> None:
        template.refresh_from_db()
        post_snapshot = self._snapshot_local_state(template)
        self.assertEqual(post_snapshot, pre_snapshot)

    def _find_event_record(self, log_ctx, event_token: str) -> logging.LogRecord:
        for record in log_ctx.records:
            if f"[TemplateSampleValidation] {event_token}:" in record.getMessage():
                return record
        self.fail(f"Expected audit-log event '{event_token}' was not emitted")


class MetaUnavailableErrorPathTest(_FailurePathAssertionMixin, _UseCaseTestBase):
    """Meta-unavailable -> ``MetaSampleUnavailableError``. Anchor: FR-005c."""

    def test_custom_api_exception_propagates_with_envelope_and_status_code(self):
        upstream_envelope = {"error": {"message": "rate limited", "code": 130472}}
        custom_exc = CustomAPIException(detail=upstream_envelope, status_code=429)
        self.meta_service.submit_template_sample.side_effect = custom_exc
        dto = self._build_dto()
        pre_snapshot = self._snapshot_local_state(self.template)

        with self.assertLogs(USECASE_LOGGER, level="ERROR") as log_ctx:
            with self.assertRaises(MetaSampleUnavailableError) as raised:
                self.use_case.execute(dto)

        exc = raised.exception
        self.assertEqual(exc.status_code, 429)
        self.assertIsNotNone(exc.meta_response)
        self.assertIn("error", exc.meta_response)

        meta_error_record = self._find_event_record(log_ctx, "meta_error")
        self.assertEqual(meta_error_record.levelno, logging.ERROR)
        self.assertIsNotNone(meta_error_record.exc_info)

        self._assert_local_state_unchanged(self.template, pre_snapshot)

    def test_unexpected_exception_propagates_without_envelope(self):
        self.meta_service.submit_template_sample.side_effect = RuntimeError(
            "socket reset"
        )
        dto = self._build_dto()
        pre_snapshot = self._snapshot_local_state(self.template)

        with self.assertLogs(USECASE_LOGGER, level="ERROR") as log_ctx:
            with self.assertRaises(MetaSampleUnavailableError) as raised:
                self.use_case.execute(dto)

        exc = raised.exception
        self.assertIsNone(exc.status_code)
        self.assertIsNone(exc.meta_response)

        meta_error_record = self._find_event_record(log_ctx, "meta_error")
        self.assertEqual(meta_error_record.levelno, logging.ERROR)
        self.assertIsNotNone(meta_error_record.exc_info)

        self._assert_local_state_unchanged(self.template, pre_snapshot)


class MetaInvalidResponseErrorPathTest(_FailurePathAssertionMixin, _UseCaseTestBase):
    """Meta 200 with unusable body -> ``MetaInvalidResponseError``. Anchor: FR-005b."""

    INVALID_META_BODIES = [
        ("success_false_with_error_envelope", {"success": False, "error": {"code": 1}}),
        ("missing_category_key", {"success": True}),
        ("empty_category_string", {"success": True, "category": ""}),
        (
            "success_false_overrides_category_present",
            {"success": False, "category": "UTILITY"},
        ),
    ]

    def test_invalid_meta_response_shapes_collapse_to_meta_invalid_response_error(self):
        dto = self._build_dto()
        for label, body in self.INVALID_META_BODIES:
            with self.subTest(case=label):
                self.meta_service.reset_mock()
                self.integrations_service.reset_mock()
                self.integrations_service.get_channel_app.return_value = {
                    "config": {"waba": {"id": _WABA_ID}}
                }
                self.meta_service.submit_template_sample.return_value = body
                pre_snapshot = self._snapshot_local_state(self.template)

                with self.assertLogs(USECASE_LOGGER, level="WARNING") as log_ctx:
                    with self.assertRaises(MetaInvalidResponseError) as raised:
                        self.use_case.execute(dto)

                self.assertEqual(raised.exception.meta_response, body)

                invalid_record = self._find_event_record(
                    log_ctx, "meta_invalid_response"
                )
                self.assertEqual(invalid_record.levelno, logging.WARNING)

                self._assert_local_state_unchanged(self.template, pre_snapshot)


class WabaNotConfiguredErrorPathTest(_FailurePathAssertionMixin, _UseCaseTestBase):
    """WABA resolution failures collapse to one error. Anchor: FR-005a / FR-008a."""

    INFRA_FAILURE_CASE = (
        "infra_failure_service_swallowed_custom_api_exception",
        None,
        False,
    )
    NOT_FOUND_CASE = (
        "integrations_returned_404_for_app_uuid",
        None,
        False,
    )
    APP_EXISTS_NO_WABA_SUBKEY = (
        "app_exists_no_waba_subkey",
        {"config": {}},
        True,
    )
    APP_EXISTS_WABA_NO_ID = (
        "app_exists_waba_no_id_key",
        {"config": {"waba": {}}},
        True,
    )
    APP_EXISTS_EMPTY_ID = (
        "app_exists_waba_id_empty_string",
        {"config": {"waba": {"id": ""}}},
        True,
    )

    INTEGRATIONS_FAILURE_CASES = [
        INFRA_FAILURE_CASE,
        NOT_FOUND_CASE,
        APP_EXISTS_NO_WABA_SUBKEY,
        APP_EXISTS_WABA_NO_ID,
        APP_EXISTS_EMPTY_ID,
    ]

    def test_waba_resolution_failures_raise_waba_not_configured_error(self):
        dto = self._build_dto()
        for (
            label,
            get_channel_app_return,
            expected_response_present,
        ) in self.INTEGRATIONS_FAILURE_CASES:
            with self.subTest(case=label):
                self.meta_service.reset_mock()
                self.integrations_service.reset_mock()
                self.integrations_service.get_channel_app.return_value = (
                    get_channel_app_return
                )
                pre_snapshot = self._snapshot_local_state(self.template)

                with patch(
                    "retail.projects.models.ProjectOnboarding.objects",
                    new=MagicMock(),
                ) as mock_onboarding_manager:
                    with self.assertLogs(USECASE_LOGGER, level="WARNING") as log_ctx:
                        with self.assertRaises(WabaNotConfiguredError):
                            self.use_case.execute(dto)

                self.integrations_service.get_channel_app.assert_called_once_with(
                    "wpp-cloud", dto.app_uuid
                )
                self.meta_service.submit_template_sample.assert_not_called()
                mock_onboarding_manager.filter.assert_not_called()
                mock_onboarding_manager.get.assert_not_called()
                mock_onboarding_manager.all.assert_not_called()

                waba_record = self._find_event_record(log_ctx, "waba_not_configured")
                self.assertEqual(waba_record.levelno, logging.WARNING)
                self.assertIn(
                    f"integrations_response_present={expected_response_present}",
                    waba_record.getMessage(),
                )
                self.assertIn(f"app_uuid={dto.app_uuid}", waba_record.getMessage())

                self._assert_local_state_unchanged(self.template, pre_snapshot)


class NotDirectSendEligibleErrorPathTest(_FailurePathAssertionMixin, _UseCaseTestBase):
    """Eligibility gate runs upstream of WABA + Meta. Anchor: FR-002a / FR-008b."""

    def test_orphan_template_without_integrated_agent_raises(self):
        orphan_template = Template.objects.create(
            uuid=uuid4(),
            name="orphan_template",
            metadata={"category": "UTILITY"},
        )
        dto = self._build_dto(template_uuid=str(orphan_template.uuid))
        pre_snapshot = self._snapshot_local_state(orphan_template)

        with self.assertLogs(USECASE_LOGGER, level="WARNING") as log_ctx:
            with self.assertRaises(NotDirectSendEligibleError):
                self.use_case.execute(dto)

        self.meta_service.submit_template_sample.assert_not_called()
        self.integrations_service.get_channel_app.assert_not_called()

        eligibility_record = self._find_event_record(
            log_ctx, "not_direct_send_eligible"
        )
        self.assertEqual(eligibility_record.levelno, logging.WARNING)
        self.assertIn("integrated_agent_uuid=None", eligibility_record.getMessage())
        self.assertIn("direct_send_flag=False", eligibility_record.getMessage())

        self._assert_local_state_unchanged(orphan_template, pre_snapshot)

    def test_empty_agent_config_raises_with_agent_uuid_logged(self):
        self.integrated_agent.config = {}
        self.integrated_agent.save(update_fields=["config"])
        dto = self._build_dto()
        pre_snapshot = self._snapshot_local_state(self.template)

        with self.assertLogs(USECASE_LOGGER, level="WARNING") as log_ctx:
            with self.assertRaises(NotDirectSendEligibleError):
                self.use_case.execute(dto)

        self.meta_service.submit_template_sample.assert_not_called()
        self.integrations_service.get_channel_app.assert_not_called()

        eligibility_record = self._find_event_record(
            log_ctx, "not_direct_send_eligible"
        )
        self.assertEqual(eligibility_record.levelno, logging.WARNING)
        self.assertIn(
            f"integrated_agent_uuid={self.integrated_agent.uuid}",
            eligibility_record.getMessage(),
        )
        self.assertIn("direct_send_flag=False", eligibility_record.getMessage())

        self._assert_local_state_unchanged(self.template, pre_snapshot)

    def test_direct_send_flag_false_raises_with_agent_uuid_logged(self):
        self.integrated_agent.config = {"direct_send": False}
        self.integrated_agent.save(update_fields=["config"])
        dto = self._build_dto()
        pre_snapshot = self._snapshot_local_state(self.template)

        with self.assertLogs(USECASE_LOGGER, level="WARNING") as log_ctx:
            with self.assertRaises(NotDirectSendEligibleError):
                self.use_case.execute(dto)

        self.meta_service.submit_template_sample.assert_not_called()
        self.integrations_service.get_channel_app.assert_not_called()

        eligibility_record = self._find_event_record(
            log_ctx, "not_direct_send_eligible"
        )
        self.assertEqual(eligibility_record.levelno, logging.WARNING)
        self.assertIn(
            f"integrated_agent_uuid={self.integrated_agent.uuid}",
            eligibility_record.getMessage(),
        )
        self.assertIn("direct_send_flag=False", eligibility_record.getMessage())

        self._assert_local_state_unchanged(self.template, pre_snapshot)


class PartialFailureAfterUtilityPathTest(_FailurePathAssertionMixin, _UseCaseTestBase):
    """Local update failure after Meta UTILITY. Anchor: FR-006c."""

    def test_strategy_failure_after_utility_propagates_and_emits_error_event(self):
        mock_strategy = MagicMock()
        mock_strategy._build_and_persist_metadata.return_value = {}
        original_exc = RuntimeError("DB write failed mid-version-create")
        mock_strategy._create_approved_current_version.side_effect = original_exc

        use_case = ValidateTemplateSampleUseCase(
            meta_service=self.meta_service,
            strategy=mock_strategy,
            metadata_handler=self.metadata_handler,
            integrations_service=self.integrations_service,
        )

        meta_sample_id = "meta-sample-id-abc123"
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
            "id": meta_sample_id,
        }
        dto = self._build_dto()

        with self.assertLogs(USECASE_LOGGER, level="ERROR") as log_ctx:
            with self.assertRaises(RuntimeError) as raised:
                use_case.execute(dto)

        self.assertIs(raised.exception, original_exc)

        failure_record = self._find_event_record(
            log_ctx, "local_update_failed_after_meta_approval"
        )
        self.assertEqual(failure_record.levelno, logging.ERROR)
        self.assertIsNotNone(failure_record.exc_info)
        self.assertIn(f"meta_sample_id={meta_sample_id}", failure_record.getMessage())


class FlaggedToApprovedRecoveryChannelTest(_UseCaseTestBase):
    """Sample endpoint as FLAGGED -> APPROVED recovery channel. Anchor: FR-008a."""

    def setUp(self):
        super().setUp()
        self.flagged_version = Version.objects.create(
            template=self.template,
            template_name="weni_order_invoiced_flagged",
            integrations_app_uuid=_DEFAULT_APP_UUID,
            project=self.project,
            status="FLAGGED",
        )
        self.template.current_version = self.flagged_version
        self.template.save(update_fields=["current_version"])

    @patch(TASK_CREATE_TEMPLATE_PATH)
    def test_flagged_template_recovers_to_approved_via_sample_endpoint(
        self, mock_task_create_template
    ):
        self.meta_service.submit_template_sample.return_value = {
            "success": True,
            "category": "UTILITY",
        }
        dto = self._build_dto()

        with self.assertLogs(USECASE_LOGGER, level="INFO") as log_ctx:
            result = self.use_case.execute(dto)

        self.template.refresh_from_db()
        new_version = self.template.current_version
        self.flagged_version.refresh_from_db()

        self.assertTrue(result.template_updated)
        self.assertEqual(new_version.status, "APPROVED")
        self.assertNotEqual(new_version.uuid, self.flagged_version.uuid)
        self.assertEqual(self.flagged_version.status, "FLAGGED")
        self.assertIn(
            self.flagged_version,
            list(self.template.versions.all()),
        )

        template_updated_record = next(
            record
            for record in log_ctx.records
            if "[TemplateSampleValidation] template_updated:" in record.getMessage()
        )
        self.assertIn(
            "previous_current_version_status=FLAGGED",
            template_updated_record.getMessage(),
        )
        self.assertIn(
            f"previous_current_version_uuid={self.flagged_version.uuid}",
            template_updated_record.getMessage(),
        )

        mock_task_create_template.delay.assert_not_called()
