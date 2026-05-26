"""Unit tests for ``ValidateTemplateSampleUseCase`` happy paths (T017 / US1).

Mocks the ``MetaService`` boundary so no live external provider is
involved (Constitution Principle III). Each test asserts the four
US1 acceptance properties:

- Local state outcome (Version + Template.current_version + metadata).
- Result wrapper shape (``category``, ``template_updated``).
- Audit-log sequence with the FR-008b log-level discipline.
- Wire-shape correctness on the outbound Meta call (for shape-specific cells).
"""

import logging
from unittest.mock import MagicMock, patch
from uuid import uuid4

from django.test import TestCase, override_settings

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.projects.models import Project
from retail.templates.exceptions import (
    NotDirectSendEligibleError,
)
from retail.templates.models import Template, Version
from retail.templates.usecases.validate_template_sample import (
    ValidateTemplateSampleDTO,
    ValidateTemplateSampleUseCase,
)


USECASE_LOGGER = "retail.templates.usecases.validate_template_sample"

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
    """Shared fixtures: Direct Send-eligible Template + mocked integrations.

    Per the 2026-05-26 clarification (FR-005a / A2), the use case now
    resolves the WABA id via ``IntegrationsService.get_channel_app(
    "wpp-cloud", app_uuid)`` instead of reading a local ``ProjectOnboarding``
    row. Tests inject a ``MagicMock(spec=IntegrationsServiceInterface)``
    whose ``get_channel_app`` returns the canonical
    ``{"config": {"waba": {"id": _WABA_ID}}}`` shape (Phase 3b).
    """

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            uuid=uuid4(), name="Test Project"
        )
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
                    record.getMessage().partition(":")[0]
                    for record in log_ctx.records
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
    """Pre-condition gate (FR-002a) — verify gating happens BEFORE Meta call."""

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
    """T036 step 3 — pin that ``ProjectOnboarding`` is never read.

    Per the 2026-05-26 clarification + data-model.md §3, the WABA-id
    resolution flows exclusively through
    ``IntegrationsService.get_channel_app(...)``. A regression that
    re-introduces a ``ProjectOnboarding.objects.*`` read would silently
    degrade the SC-008 / FR-005a guarantee that the integrations engine
    is the sole authoritative source for channel-app state.
    """

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
