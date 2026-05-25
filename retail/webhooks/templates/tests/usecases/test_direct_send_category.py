import logging
import re

from unittest.mock import patch
from uuid import uuid4

from django.test import TestCase

from retail.agents.domains.agent_integration.models import IntegratedAgent
from retail.agents.domains.agent_management.models import Agent
from retail.projects.models import Project
from retail.templates.models import Template, Version
from retail.webhooks.templates.usecases.direct_send_category import (
    DirectSendCategoryDTO,
    DirectSendCategoryWebhookUseCase,
    EventName,
    FlaggingReason,
)


# Shared key set for outcomes that observe an existing Version without
# writing to it: the full inbound payload plus the resolved
# IntegratedAgent / Template / Version identifiers and the unchanged
# ``previous_status``. ``flagged`` writes and therefore adds
# ``new_status`` + ``reason``; the no-write outcomes below do not.
_NO_WRITE_OUTCOME_KEYS = {
    "project_uuid",
    "app_uuid",
    "template_name",
    "template_category",
    "template_correct_category",
    "integrated_agent_uuid",
    "template_uuid",
    "version_uuid",
    "previous_status",
}

EXPECTED_KEYS_BY_EVENT = {
    EventName.RECEIVED.value: {
        "project_uuid",
        "app_uuid",
        "template_name",
        "template_category",
        "template_correct_category",
    },
    EventName.FLAGGED.value: {
        "project_uuid",
        "app_uuid",
        "template_name",
        "template_category",
        "template_correct_category",
        "integrated_agent_uuid",
        "template_uuid",
        "version_uuid",
        "previous_status",
        "new_status",
        "reason",
    },
    EventName.NO_ACTION_REQUIRED.value: _NO_WRITE_OUTCOME_KEYS,
    EventName.FLAG_REPLAY_NOOP.value: _NO_WRITE_OUTCOME_KEYS,
    EventName.NO_ACTION_REQUIRED_ALREADY_FLAGGED.value: _NO_WRITE_OUTCOME_KEYS,
    EventName.COMPLETED.value: {
        "project_uuid",
        "app_uuid",
        "template_name",
        "templates_updated",
        "integrated_agents_inspected",
    },
    EventName.NO_MATCHING_INTEGRATED_AGENT.value: {
        "project_uuid",
        "app_uuid",
        "template_name",
        "template_category",
        "template_correct_category",
    },
    EventName.TEMPLATE_NOT_FOUND.value: {
        "project_uuid",
        "app_uuid",
        "template_name",
        "integrated_agent_uuid",
    },
    EventName.TEMPLATE_HAS_NO_CURRENT_VERSION.value: {
        "project_uuid",
        "app_uuid",
        "template_name",
        "integrated_agent_uuid",
        "template_uuid",
    },
}

_EVENT_NAME_REGEX = re.compile(r"\[DirectSendCategoryWebhook\] (?P<event>\w+):")


def _event_of(record: logging.LogRecord) -> str:
    match = _EVENT_NAME_REGEX.match(record.getMessage())
    if match is None:
        raise AssertionError(f"Unexpected log line: {record.getMessage()}")
    return match.group("event")


def _records_by_event(records):
    grouped = {}
    for record in records:
        grouped.setdefault(_event_of(record), []).append(record)
    return grouped


class _UseCaseTestBase(TestCase):
    APP_UUID = "22222222-2222-2222-2222-222222222222"
    TEMPLATE_NAME = "weni_order_invoiced"

    def setUp(self):
        super().setUp()
        self.project = Project.objects.create(
            name="Acme", uuid="11111111-1111-1111-1111-111111111111"
        )
        self.agent = Agent.objects.create(
            project=self.project,
            name="OrderStatus",
            slug="order-status",
            description="desc",
        )
        self.integrated_agent = self._create_integrated_agent(self.project)
        self.template = self._create_template(self.integrated_agent, self.TEMPLATE_NAME)
        self.version = self._create_version(
            self.template, self.project, self.APP_UUID, status="APPROVED"
        )
        self._link_current_version(self.template, self.version)

        self.usecase = DirectSendCategoryWebhookUseCase()

    def _create_integrated_agent(self, project):
        return IntegratedAgent.objects.create(
            agent=self.agent, project=project, uuid=uuid4()
        )

    def _create_template(self, integrated_agent, name):
        return Template.objects.create(
            name=name, integrated_agent=integrated_agent, uuid=uuid4()
        )

    def _create_version(self, template, project, app_uuid, status="APPROVED"):
        return Version.objects.create(
            template=template,
            template_name=template.name,
            integrations_app_uuid=app_uuid,
            project=project,
            status=status,
        )

    def _link_current_version(self, template, version):
        template.current_version = version
        template.save(update_fields=["current_version"])

    def _build_dto(
        self,
        template_category="MARKETING",
        template_correct_category="MARKETING",
        project_uuid=None,
        app_uuid=None,
        template_name=None,
    ):
        return DirectSendCategoryDTO(
            project_uuid=project_uuid or self.project.uuid,
            app_uuid=app_uuid or self.APP_UUID,
            template_name=template_name or self.TEMPLATE_NAME,
            template_category=template_category,
            template_correct_category=template_correct_category,
        )


class _VersionSaveSpy:
    """Spy on ``Version.save`` that records every call and delegates to
    the real method so the DB write still happens.

    ``unittest.mock.patch.object(Version, "save", autospec=True, wraps=...)``
    does not bind ``self`` reliably across mock versions, so we monkey-patch
    with a plain function and record call args explicitly.
    """

    def __init__(self):
        self._original = Version.save
        self.calls = []

    def __enter__(self):
        spy = self

        def replacement(version_self, *args, **kwargs):
            spy.calls.append({"self": version_self, "args": args, "kwargs": kwargs})
            return spy._original(version_self, *args, **kwargs)

        self._patcher = patch.object(Version, "save", replacement)
        self._patcher.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._patcher.stop()

    @property
    def call_count(self):
        return len(self.calls)

    @property
    def last_call_kwargs(self):
        return self.calls[-1]["kwargs"] if self.calls else None


class FlaggingPathTest(_UseCaseTestBase):
    REASON_SCENARIOS = [
        ("UTILITY", "MARKETING", FlaggingReason.CATEGORY_MISMATCH),
        ("MARKETING", "MARKETING", FlaggingReason.CATEGORY_NOT_UTILITY),
        (
            "MARKETING",
            "AUTHENTICATION",
            FlaggingReason.CATEGORY_MISMATCH_AND_NOT_UTILITY,
        ),
    ]
    PREVIOUS_STATUSES = ["APPROVED", "PAUSED", "PENDING", "REJECTED", "DELETED"]

    def test_flagging_condition_writes_flagged_for_every_reason_and_previous_status(
        self,
    ):
        for category, correct, expected_reason in self.REASON_SCENARIOS:
            for previous_status in self.PREVIOUS_STATUSES:
                with self.subTest(
                    category=category,
                    correct=correct,
                    previous_status=previous_status,
                ):
                    Version.objects.filter(pk=self.version.pk).update(
                        status=previous_status
                    )
                    self.version.refresh_from_db()
                    self.template.refresh_from_db()
                    original_current_version_id = self.template.current_version_id

                    with _VersionSaveSpy() as save_spy:
                        dto = self._build_dto(
                            template_category=category,
                            template_correct_category=correct,
                        )
                        with self.assertLogs(
                            "retail.webhooks.templates.usecases.direct_send_category",
                            level="INFO",
                        ) as log_ctx:
                            result = self.usecase.execute(dto)

                    self.version.refresh_from_db()
                    self.template.refresh_from_db()

                    self.assertEqual(self.version.status, "FLAGGED")
                    self.assertEqual(
                        self.template.current_version_id,
                        original_current_version_id,
                    )
                    self.assertEqual(result.templates_updated, 1)
                    self.assertEqual(result.integrated_agents_inspected, 1)
                    self.assertEqual(result.detail, "Templates flagged.")

                    self.assertEqual(save_spy.call_count, 1)
                    self.assertEqual(
                        save_spy.last_call_kwargs.get("update_fields"), ["status"]
                    )

                    flagged_records = _records_by_event(log_ctx.records)["flagged"]
                    self.assertEqual(len(flagged_records), 1)
                    self.assertEqual(
                        flagged_records[0].args["reason"], expected_reason.value
                    )
                    self.assertEqual(
                        flagged_records[0].args["previous_status"], previous_status
                    )

    def test_utility_payload_skips_save_and_emits_no_action_required(self):
        with _VersionSaveSpy() as save_spy:
            dto = self._build_dto(
                template_category="UTILITY", template_correct_category="UTILITY"
            )
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="INFO",
            ) as log_ctx:
                result = self.usecase.execute(dto)

        self.assertEqual(save_spy.call_count, 0)
        self.assertEqual(result.templates_updated, 0)
        self.assertEqual(result.integrated_agents_inspected, 1)
        self.assertEqual(result.detail, "No action required.")

        events = _records_by_event(log_ctx.records)
        self.assertIn("no_action_required", events)
        self.assertNotIn("flagged", events)

    def test_received_and_completed_lines_emitted_exactly_once_with_payload(self):
        dto = self._build_dto()
        with self.assertLogs(
            "retail.webhooks.templates.usecases.direct_send_category",
            level="INFO",
        ) as log_ctx:
            self.usecase.execute(dto)

        events = _records_by_event(log_ctx.records)
        self.assertEqual(len(events["received"]), 1)
        self.assertEqual(len(events["completed"]), 1)

        received = events["received"][0]
        self.assertEqual(received.args["project_uuid"], dto.project_uuid)
        self.assertEqual(received.args["app_uuid"], dto.app_uuid)
        self.assertEqual(received.args["template_name"], dto.template_name)
        self.assertEqual(received.args["template_category"], dto.template_category)
        self.assertEqual(
            received.args["template_correct_category"],
            dto.template_correct_category,
        )

        completed = events["completed"][0]
        self.assertEqual(completed.args["templates_updated"], 1)
        self.assertEqual(completed.args["integrated_agents_inspected"], 1)

    def test_audit_payload_keys_match_fr_009d_for_each_event(self):
        dto = self._build_dto()
        with self.assertLogs(
            "retail.webhooks.templates.usecases.direct_send_category",
            level="INFO",
        ) as log_ctx:
            self.usecase.execute(dto)

        for record in log_ctx.records:
            event = _event_of(record)
            expected_keys = EXPECTED_KEYS_BY_EVENT[event]
            self.assertEqual(
                set(record.args.keys()),
                expected_keys,
                f"Event {event!r} carries unexpected keys",
            )


class CounterParityTest(_UseCaseTestBase):
    def test_completed_log_counters_equal_result_counters(self):
        dto = self._build_dto()
        with self.assertLogs(
            "retail.webhooks.templates.usecases.direct_send_category",
            level="INFO",
        ) as log_ctx:
            result = self.usecase.execute(dto)

        completed = _records_by_event(log_ctx.records)["completed"][0]
        self.assertEqual(completed.args["templates_updated"], result.templates_updated)
        self.assertEqual(
            completed.args["integrated_agents_inspected"],
            result.integrated_agents_inspected,
        )


class MultiIntegratedAgentFanOutTest(_UseCaseTestBase):
    def setUp(self):
        super().setUp()
        self.second_ia = self._create_integrated_agent(self.project)
        self.second_template = self._create_template(self.second_ia, self.TEMPLATE_NAME)
        self.second_version = self._create_version(
            self.second_template,
            self.project,
            self.APP_UUID,
            status="APPROVED",
        )
        self._link_current_version(self.second_template, self.second_version)

    def test_two_integrated_agents_both_flagged(self):
        dto = self._build_dto()
        result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.second_version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")
        self.assertEqual(self.second_version.status, "FLAGGED")
        self.assertEqual(result.templates_updated, 2)
        self.assertEqual(result.integrated_agents_inspected, 2)
        self.assertEqual(result.detail, "Templates flagged.")


class CrossTenantIsolationTest(_UseCaseTestBase):
    def test_integrated_agent_in_other_project_is_excluded(self):
        other_project = Project.objects.create(
            name="Other", uuid="99999999-9999-9999-9999-999999999999"
        )
        other_ia = IntegratedAgent.objects.create(
            agent=self.agent, project=other_project, uuid=uuid4()
        )
        other_template = self._create_template(other_ia, self.TEMPLATE_NAME)
        other_version = self._create_version(
            other_template, other_project, self.APP_UUID, status="APPROVED"
        )
        self._link_current_version(other_template, other_version)

        dto = self._build_dto()
        with self.assertLogs(
            "retail.webhooks.templates.usecases.direct_send_category",
            level="INFO",
        ) as log_ctx:
            result = self.usecase.execute(dto)

        other_version.refresh_from_db()
        self.assertEqual(other_version.status, "APPROVED")
        self.assertEqual(result.integrated_agents_inspected, 1)

        for record in log_ctx.records:
            self.assertNotIn(str(other_ia.uuid), record.getMessage())
            self.assertNotIn(str(other_template.uuid), record.getMessage())


class BlockedProjectStillProcessesTest(_UseCaseTestBase):
    def test_blocked_project_still_flags_version(self):
        self.project.is_blocked = True
        self.project.save(update_fields=["is_blocked"])

        dto = self._build_dto()
        with self.assertLogs(
            "retail.webhooks.templates.usecases.direct_send_category",
            level="INFO",
        ) as log_ctx:
            result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")
        self.assertEqual(result.templates_updated, 1)

        flagged = _records_by_event(log_ctx.records)["flagged"][0]
        expected_keys = EXPECTED_KEYS_BY_EVENT[EventName.FLAGGED.value]
        self.assertEqual(set(flagged.args.keys()), expected_keys)


class AuditPayloadNoTruncationTest(_UseCaseTestBase):
    def test_long_template_correct_category_is_recorded_verbatim(self):
        long_value = "X" * 200
        dto = self._build_dto(
            template_category="MARKETING", template_correct_category=long_value
        )

        with self.assertLogs(
            "retail.webhooks.templates.usecases.direct_send_category",
            level="INFO",
        ) as log_ctx:
            self.usecase.execute(dto)

        flagged = _records_by_event(log_ctx.records)["flagged"][0]
        self.assertEqual(set(flagged.args.keys()), EXPECTED_KEYS_BY_EVENT["flagged"])
        self.assertEqual(flagged.args["template_correct_category"], long_value)
        self.assertIn(long_value, flagged.getMessage())


class _AlreadyFlaggedTestBase(_UseCaseTestBase):
    """Shared fixture: the Version is already FLAGGED before each test runs."""

    def setUp(self):
        super().setUp()
        Version.objects.filter(pk=self.version.pk).update(status="FLAGGED")
        self.version.refresh_from_db()


class IdempotentReplayWithFlaggingPayloadTest(_AlreadyFlaggedTestBase):
    def test_replay_emits_flag_replay_noop_and_skips_save(self):
        with _VersionSaveSpy() as save_spy:
            dto = self._build_dto(
                template_category="MARKETING",
                template_correct_category="MARKETING",
            )
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="INFO",
            ) as log_ctx:
                result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")
        self.assertEqual(save_spy.call_count, 0)
        self.assertEqual(result.templates_updated, 0)
        self.assertEqual(result.integrated_agents_inspected, 1)
        self.assertEqual(result.detail, "Already flagged.")

        events = _records_by_event(log_ctx.records)
        self.assertIn("flag_replay_noop", events)
        self.assertNotIn("flagged", events)

        replay = events["flag_replay_noop"][0]
        self.assertEqual(replay.levelno, logging.INFO)
        self.assertEqual(
            set(replay.args.keys()),
            EXPECTED_KEYS_BY_EVENT[EventName.FLAG_REPLAY_NOOP.value],
        )
        self.assertNotIn("new_status", replay.args)
        self.assertNotIn("reason", replay.args)
        self.assertEqual(replay.args["previous_status"], "FLAGGED")


class IdempotentReplayWithNonFlaggingPayloadTest(_AlreadyFlaggedTestBase):
    def test_replay_emits_no_action_required_already_flagged_and_skips_save(self):
        with _VersionSaveSpy() as save_spy:
            dto = self._build_dto(
                template_category="UTILITY",
                template_correct_category="UTILITY",
            )
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="INFO",
            ) as log_ctx:
                result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")
        self.assertEqual(save_spy.call_count, 0)
        self.assertEqual(result.templates_updated, 0)
        self.assertEqual(result.integrated_agents_inspected, 1)
        self.assertEqual(result.detail, "Already flagged.")

        events = _records_by_event(log_ctx.records)
        self.assertIn("no_action_required_already_flagged", events)
        self.assertNotIn("flagged", events)
        self.assertNotIn("no_action_required", events)

        replay = events["no_action_required_already_flagged"][0]
        self.assertEqual(replay.levelno, logging.INFO)
        self.assertEqual(
            set(replay.args.keys()),
            EXPECTED_KEYS_BY_EVENT[EventName.NO_ACTION_REQUIRED_ALREADY_FLAGGED.value],
        )
        self.assertNotIn("new_status", replay.args)
        self.assertNotIn("reason", replay.args)
        self.assertEqual(replay.args["previous_status"], "FLAGGED")


class ConsecutiveCallsConvergeIdempotentlyTest(_UseCaseTestBase):
    def test_first_call_flags_and_second_call_replays_without_writing(self):
        dto = self._build_dto(
            template_category="MARKETING",
            template_correct_category="MARKETING",
        )

        with _VersionSaveSpy() as save_spy:
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="INFO",
            ) as log_ctx:
                first_result = self.usecase.execute(dto)
                second_result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")
        self.assertEqual(save_spy.call_count, 1)
        self.assertEqual(save_spy.last_call_kwargs.get("update_fields"), ["status"])

        self.assertEqual(first_result.templates_updated, 1)
        self.assertEqual(first_result.detail, "Templates flagged.")
        self.assertEqual(second_result.templates_updated, 0)
        self.assertEqual(second_result.detail, "Already flagged.")

        events = _records_by_event(log_ctx.records)
        self.assertEqual(len(events["flagged"]), 1)
        self.assertEqual(len(events["flag_replay_noop"]), 1)
        self.assertEqual(len(events["received"]), 2)
        self.assertEqual(len(events["completed"]), 2)


class ReplayWithChangedCorrectCategoryTest(_UseCaseTestBase):
    """Edge Case row 7: an existing FLAGGED state must absorb a follow-up
    detection whose payload carries a different ``template_correct_category``
    without re-issuing the UPDATE or emitting a second ``flagged`` line."""

    def test_replay_with_new_correct_category_emits_flag_replay_noop(self):
        first_dto = self._build_dto(
            template_category="MARKETING",
            template_correct_category="MARKETING",
        )
        second_dto = self._build_dto(
            template_category="MARKETING",
            template_correct_category="AUTHENTICATION",
        )

        with _VersionSaveSpy() as save_spy:
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="INFO",
            ) as log_ctx:
                self.usecase.execute(first_dto)
                self.usecase.execute(second_dto)

        self.assertEqual(save_spy.call_count, 1)

        events = _records_by_event(log_ctx.records)
        self.assertEqual(len(events["flagged"]), 1)
        self.assertEqual(len(events["flag_replay_noop"]), 1)

        replay = events["flag_replay_noop"][0]
        self.assertEqual(replay.args["previous_status"], "FLAGGED")
        self.assertEqual(replay.args["template_correct_category"], "AUTHENTICATION")
        self.assertEqual(replay.args["template_category"], "MARKETING")


class NoMatchingIntegratedAgentTest(_UseCaseTestBase):
    """FR-004b — when the lookup returns zero IntegratedAgents, the
    response is HTTP 200 with zero counters and the audit log records
    a single WARNING-level ``no_matching_integrated_agent`` line that
    carries only the five payload values (no IA / Template / Version
    identifiers because none were resolved)."""

    def test_no_match_emits_warning_and_returns_zero_counters(self):
        unrelated_app_uuid = uuid4()

        with _VersionSaveSpy() as save_spy:
            dto = self._build_dto(app_uuid=unrelated_app_uuid)
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="WARNING",
            ) as log_ctx:
                result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "APPROVED")
        self.assertEqual(save_spy.call_count, 0)

        self.assertEqual(result.templates_updated, 0)
        self.assertEqual(result.integrated_agents_inspected, 0)
        self.assertEqual(result.detail, "No matching IntegratedAgent.")

        events = _records_by_event(log_ctx.records)
        self.assertIn("no_matching_integrated_agent", events)

        record = events["no_matching_integrated_agent"][0]
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertEqual(
            set(record.args.keys()),
            EXPECTED_KEYS_BY_EVENT[EventName.NO_MATCHING_INTEGRATED_AGENT.value],
        )
        for forbidden_key in (
            "integrated_agent_uuid",
            "template_uuid",
            "version_uuid",
        ):
            self.assertNotIn(forbidden_key, record.args)


class TemplateNotFoundTest(_UseCaseTestBase):
    """FR-005 — when a matched IntegratedAgent has no Template with the
    requested name, the use case emits a WARNING-level
    ``template_not_found`` line, skips the write, and reports
    ``"Template not found."``."""

    def test_template_not_found_emits_warning_and_skips_save(self):
        unknown_template_name = "weni_unknown_template"

        with _VersionSaveSpy() as save_spy:
            dto = self._build_dto(template_name=unknown_template_name)
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="WARNING",
            ) as log_ctx:
                result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "APPROVED")
        self.assertEqual(save_spy.call_count, 0)

        self.assertEqual(result.templates_updated, 0)
        self.assertEqual(result.integrated_agents_inspected, 1)
        self.assertEqual(result.detail, "Template not found.")

        events = _records_by_event(log_ctx.records)
        self.assertIn("template_not_found", events)

        record = events["template_not_found"][0]
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertEqual(
            set(record.args.keys()),
            EXPECTED_KEYS_BY_EVENT[EventName.TEMPLATE_NOT_FOUND.value],
        )
        self.assertEqual(record.args["template_name"], unknown_template_name)
        self.assertEqual(
            record.args["integrated_agent_uuid"], self.integrated_agent.uuid
        )


class TemplateHasNoCurrentVersionTest(_UseCaseTestBase):
    """FR-005a — when a matched Template has ``current_version=None``
    (an inconsistent local state — defensively guarded), the use case
    emits a WARNING-level ``template_has_no_current_version`` line,
    skips the write, and the response ``detail`` collapses to
    ``"Template not found."`` per data-model §5.2 footnote *."""

    def test_null_current_version_emits_warning_and_skips_save(self):
        self.template.current_version = None
        self.template.save(update_fields=["current_version"])

        with _VersionSaveSpy() as save_spy:
            dto = self._build_dto()
            with self.assertLogs(
                "retail.webhooks.templates.usecases.direct_send_category",
                level="WARNING",
            ) as log_ctx:
                result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.assertEqual(self.version.status, "APPROVED")
        self.assertEqual(save_spy.call_count, 0)

        self.assertEqual(result.templates_updated, 0)
        self.assertEqual(result.integrated_agents_inspected, 1)
        self.assertEqual(result.detail, "Template not found.")

        events = _records_by_event(log_ctx.records)
        self.assertIn("template_has_no_current_version", events)

        record = events["template_has_no_current_version"][0]
        self.assertEqual(record.levelno, logging.WARNING)
        self.assertEqual(
            set(record.args.keys()),
            EXPECTED_KEYS_BY_EVENT[EventName.TEMPLATE_HAS_NO_CURRENT_VERSION.value],
        )
        self.assertEqual(record.args["template_uuid"], self.template.uuid)
        self.assertEqual(
            record.args["integrated_agent_uuid"], self.integrated_agent.uuid
        )


class MixedOutcomesFanOutTest(_UseCaseTestBase):
    """Contract §6.6 — when the per-IA outcomes are not all the same
    (e.g. IA-1 flags, IA-2 has no matching Template), the response
    ``detail`` collapses to ``"Mixed outcomes."`` and one audit line
    fires per IntegratedAgent inspected."""

    OTHER_TEMPLATE_NAME = "weni_other_template"

    def setUp(self):
        super().setUp()
        self.second_ia = self._create_integrated_agent(self.project)
        self.second_template = self._create_template(
            self.second_ia, self.OTHER_TEMPLATE_NAME
        )
        self.second_version = self._create_version(
            self.second_template,
            self.project,
            self.APP_UUID,
            status="APPROVED",
        )
        self._link_current_version(self.second_template, self.second_version)

    def test_one_ia_flags_one_ia_template_not_found(self):
        dto = self._build_dto(
            template_category="MARKETING",
            template_correct_category="MARKETING",
        )
        with self.assertLogs(
            "retail.webhooks.templates.usecases.direct_send_category",
            level="INFO",
        ) as log_ctx:
            result = self.usecase.execute(dto)

        self.version.refresh_from_db()
        self.second_version.refresh_from_db()
        self.assertEqual(self.version.status, "FLAGGED")
        self.assertEqual(self.second_version.status, "APPROVED")

        self.assertEqual(result.templates_updated, 1)
        self.assertEqual(result.integrated_agents_inspected, 2)
        self.assertEqual(result.detail, "Mixed outcomes.")

        events = _records_by_event(log_ctx.records)
        self.assertEqual(len(events["flagged"]), 1)
        self.assertEqual(len(events["template_not_found"]), 1)

        flagged = events["flagged"][0]
        self.assertEqual(flagged.levelno, logging.INFO)
        self.assertEqual(
            flagged.args["integrated_agent_uuid"], self.integrated_agent.uuid
        )

        not_found = events["template_not_found"][0]
        self.assertEqual(not_found.levelno, logging.WARNING)
        self.assertEqual(not_found.args["integrated_agent_uuid"], self.second_ia.uuid)
