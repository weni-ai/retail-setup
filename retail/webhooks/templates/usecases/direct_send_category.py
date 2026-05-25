import logging
from dataclasses import dataclass
from enum import Enum
from uuid import UUID

from retail.agents.domains.agent_integration.models import IntegratedAgent


logger = logging.getLogger(__name__)

LOG_TAG = "[DirectSendCategoryWebhook]"


@dataclass(frozen=True)
class DirectSendCategoryDTO:
    """Validated, immutable payload passed from the view to the use case.

    Built by the view from the serializer's ``validated_data``;
    consumed by ``DirectSendCategoryWebhookUseCase.execute(...)``.
    Carries the five required fields pinned by FR-003.
    """

    project_uuid: UUID
    app_uuid: UUID
    template_name: str
    template_category: str
    template_correct_category: str


@dataclass(frozen=True)
class DirectSendCategoryResult:
    """Use-case return value shaped for the HTTP 200 response body.

    The view shapes the HTTP body as ``Response(result.to_dict(), 200)``.
    The two counters MUST equal the same values emitted on the
    FR-009c ``completed`` audit-log line (FR-010 last sentence).
    """

    templates_updated: int
    integrated_agents_inspected: int
    detail: str

    def to_dict(self) -> dict:
        return {
            "detail": self.detail,
            "templates_updated": self.templates_updated,
            "integrated_agents_inspected": self.integrated_agents_inspected,
        }


class FlaggingReason(str, Enum):
    """Closed enumeration for the ``reason=`` k=v on ``flagged`` audit-log lines.

    Pinned by FR-006b / FR-009a. Additive-only: new reasons MAY be
    added; existing reasons MUST NOT be renamed or removed.
    """

    CATEGORY_MISMATCH = "category_mismatch"
    CATEGORY_NOT_UTILITY = "category_not_utility"
    CATEGORY_MISMATCH_AND_NOT_UTILITY = "category_mismatch_and_not_utility"


class EventName(str, Enum):
    """Closed enumeration for the ``event_name`` discriminator immediately
    after the ``[DirectSendCategoryWebhook]`` tag in every audit-log line.

    Pinned by FR-009a. Additive-only.
    """

    RECEIVED = "received"
    FLAGGED = "flagged"
    FLAG_REPLAY_NOOP = "flag_replay_noop"
    NO_ACTION_REQUIRED = "no_action_required"
    AUTO_DEMOTED = "auto_demoted"
    NO_MATCHING_INTEGRATED_AGENT = "no_matching_integrated_agent"
    TEMPLATE_NOT_FOUND = "template_not_found"
    TEMPLATE_HAS_NO_CURRENT_VERSION = "template_has_no_current_version"
    COMPLETED = "completed"
    UNEXPECTED_ERROR = "unexpected_error"


class DirectSendCategoryWebhookUseCase:
    """Handles incorrect-category notifications from Integrations.

    Fans out across every IntegratedAgent linked to ``(project_uuid, app_uuid)``
    and flips the matched Template's ``current_version.status`` to
    ``"FLAGGED"`` when the FR-006 two-clause flagging condition fires.
    Framework-agnostic: no rest_framework imports, no Response/Request
    handling, no permission checks.
    """

    _UTILITY_CATEGORY = "UTILITY"
    _FLAGGED_STATUS = "FLAGGED"
    _APPROVED_STATUS = "APPROVED"

    _OUTCOME_TO_DETAIL = {
        "flagged": "Templates flagged.",
        "no_action_required": "No action required.",
        "flag_replay_noop": "Already flagged.",
        "auto_demoted": "Auto-demoted.",
        "template_not_found": "Template not found.",
        "template_has_no_current_version": "Template not found.",
    }

    def execute(self, dto: DirectSendCategoryDTO) -> DirectSendCategoryResult:
        self._emit_received(dto)

        try:
            integrated_agents = list(self._lookup_integrated_agents(dto))

            if not integrated_agents:
                self._emit_no_matching_integrated_agent(dto)
                result = DirectSendCategoryResult(
                    templates_updated=0,
                    integrated_agents_inspected=0,
                    detail="No matching IntegratedAgent.",
                )
                self._emit_completed(dto, result)
                return result

            inspected = 0
            templates_updated = 0
            outcomes: list[str] = []
            for integrated_agent in integrated_agents:
                inspected += 1
                template = self._lookup_template(integrated_agent, dto.template_name)
                if template is None:
                    self._emit_template_not_found(integrated_agent, dto)
                    outcomes.append("template_not_found")
                    continue
                if template.current_version is None:
                    self._emit_template_has_no_current_version(
                        integrated_agent, template, dto
                    )
                    outcomes.append("template_has_no_current_version")
                    continue

                version = template.current_version
                flagging_condition_met = self._evaluate_flagging_condition(dto)

                if version.status == self._FLAGGED_STATUS:
                    if flagging_condition_met:
                        self._emit_flag_replay_noop(
                            integrated_agent, template, version, dto
                        )
                        outcomes.append("flag_replay_noop")
                    else:
                        self._demote_version(version, template, integrated_agent, dto)
                        templates_updated += 1
                        outcomes.append("auto_demoted")
                    continue

                if flagging_condition_met:
                    reason = self._determine_flagging_reason(dto)
                    self._flag_version(version, template, integrated_agent, dto, reason)
                    templates_updated += 1
                    outcomes.append("flagged")
                else:
                    self._emit_no_action_required(
                        integrated_agent, template, version, dto
                    )
                    outcomes.append("no_action_required")

            result = DirectSendCategoryResult(
                templates_updated=templates_updated,
                integrated_agents_inspected=inspected,
                detail=self._determine_detail(outcomes),
            )
            self._emit_completed(dto, result)
            return result
        except Exception as exc:
            self._emit_unexpected_error(dto, exc)
            raise

    def _lookup_integrated_agents(self, dto: DirectSendCategoryDTO):
        return IntegratedAgent.objects.filter(
            project__uuid=dto.project_uuid,
            templates__versions__integrations_app_uuid=dto.app_uuid,
        ).distinct()

    def _lookup_template(self, integrated_agent: IntegratedAgent, template_name: str):
        return (
            integrated_agent.templates.select_related("current_version")
            .filter(name=template_name)
            .first()
        )

    def _evaluate_flagging_condition(self, dto: DirectSendCategoryDTO) -> bool:
        return (
            dto.template_category != dto.template_correct_category
            or dto.template_category != self._UTILITY_CATEGORY
        )

    def _determine_flagging_reason(self, dto: DirectSendCategoryDTO) -> FlaggingReason:
        category_mismatch = dto.template_category != dto.template_correct_category
        not_utility = dto.template_category != self._UTILITY_CATEGORY

        if category_mismatch and not_utility:
            return FlaggingReason.CATEGORY_MISMATCH_AND_NOT_UTILITY
        if category_mismatch:
            return FlaggingReason.CATEGORY_MISMATCH
        return FlaggingReason.CATEGORY_NOT_UTILITY

    def _flag_version(
        self,
        version,
        template,
        integrated_agent: IntegratedAgent,
        dto: DirectSendCategoryDTO,
        reason: FlaggingReason,
    ) -> None:
        previous_status = version.status
        version.status = self._FLAGGED_STATUS
        version.save(update_fields=["status"])
        self._emit_flagged(
            integrated_agent, template, version, dto, previous_status, reason
        )

    def _demote_version(
        self,
        version,
        template,
        integrated_agent: IntegratedAgent,
        dto: DirectSendCategoryDTO,
    ) -> None:
        """Write the corrected-category recovery transition.

        FR-006c / FR-007c clause (b) / FR-007d: when the matched
        Version is already ``"FLAGGED"`` AND the FR-006 flagging
        condition is false (the corrected-category signal —
        ``template_category == template_correct_category == "UTILITY"``),
        the webhook writes ``status = "APPROVED"`` and emits
        ``auto_demoted``. The Template's ``current_version`` pointer
        is NOT changed (FR-007a applies symmetrically to the demote
        branch — only the status string is updated).
        """
        previous_status = version.status
        version.status = self._APPROVED_STATUS
        version.save(update_fields=["status"])
        self._emit_auto_demoted(
            integrated_agent, template, version, dto, previous_status
        )

    def _determine_detail(self, outcomes: list) -> str:
        groups = {self._OUTCOME_TO_DETAIL[outcome] for outcome in outcomes}
        if len(groups) == 1:
            return next(iter(groups))
        return "Mixed outcomes."

    def _emit(self, event: EventName, level: int, **kv) -> None:
        """Single emission point that knows the FR-009 log-line shape.

        Every audit-log entry for this webhook MUST route through this
        method — the ``[DirectSendCategoryWebhook]`` tag, the
        ``event_name: k=v ...`` shape, and the log-level discipline are
        enforced structurally here so callers cannot drift from FR-009.

        The fully-formatted message is built up front so the rendered log
        line carries the FR-009 ``k=v`` pairs verbatim. The same payload
        is also forwarded as a dict via the logging stdlib's ``args``
        slot so operator dashboards (and FR-009e tests) can inspect the
        structured payload via ``record.args.keys()`` without re-parsing
        the rendered string.
        """
        payload = " ".join(f"{key}={value}" for key, value in kv.items())
        message = f"{LOG_TAG} {event.value}: {payload}".replace("%", "%%")
        if level == logging.ERROR:
            logger.error(message, kv, exc_info=True)
        elif level == logging.WARNING:
            logger.warning(message, kv)
        else:
            logger.info(message, kv)

    def _emit_received(self, dto: DirectSendCategoryDTO) -> None:
        self._emit(
            EventName.RECEIVED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            template_category=dto.template_category,
            template_correct_category=dto.template_correct_category,
        )

    def _emit_flagged(
        self,
        integrated_agent: IntegratedAgent,
        template,
        version,
        dto: DirectSendCategoryDTO,
        previous_status: str,
        reason: FlaggingReason,
    ) -> None:
        self._emit(
            EventName.FLAGGED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            template_category=dto.template_category,
            template_correct_category=dto.template_correct_category,
            integrated_agent_uuid=integrated_agent.uuid,
            template_uuid=template.uuid,
            version_uuid=version.uuid,
            previous_status=previous_status,
            new_status=self._FLAGGED_STATUS,
            reason=reason.value,
        )

    def _emit_no_action_required(
        self,
        integrated_agent: IntegratedAgent,
        template,
        version,
        dto: DirectSendCategoryDTO,
    ) -> None:
        self._emit(
            EventName.NO_ACTION_REQUIRED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            template_category=dto.template_category,
            template_correct_category=dto.template_correct_category,
            integrated_agent_uuid=integrated_agent.uuid,
            template_uuid=template.uuid,
            version_uuid=version.uuid,
            previous_status=version.status,
        )

    def _emit_flag_replay_noop(
        self,
        integrated_agent: IntegratedAgent,
        template,
        version,
        dto: DirectSendCategoryDTO,
    ) -> None:
        self._emit(
            EventName.FLAG_REPLAY_NOOP,
            logging.INFO,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            template_category=dto.template_category,
            template_correct_category=dto.template_correct_category,
            integrated_agent_uuid=integrated_agent.uuid,
            template_uuid=template.uuid,
            version_uuid=version.uuid,
            previous_status=version.status,
        )

    def _emit_auto_demoted(
        self,
        integrated_agent: IntegratedAgent,
        template,
        version,
        dto: DirectSendCategoryDTO,
        previous_status: str,
    ) -> None:
        self._emit(
            EventName.AUTO_DEMOTED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            template_category=dto.template_category,
            template_correct_category=dto.template_correct_category,
            integrated_agent_uuid=integrated_agent.uuid,
            template_uuid=template.uuid,
            version_uuid=version.uuid,
            previous_status=previous_status,
            new_status=self._APPROVED_STATUS,
        )

    def _emit_no_matching_integrated_agent(self, dto: DirectSendCategoryDTO) -> None:
        self._emit(
            EventName.NO_MATCHING_INTEGRATED_AGENT,
            logging.WARNING,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            template_category=dto.template_category,
            template_correct_category=dto.template_correct_category,
        )

    def _emit_template_not_found(
        self, integrated_agent: IntegratedAgent, dto: DirectSendCategoryDTO
    ) -> None:
        self._emit(
            EventName.TEMPLATE_NOT_FOUND,
            logging.WARNING,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            integrated_agent_uuid=integrated_agent.uuid,
        )

    def _emit_template_has_no_current_version(
        self,
        integrated_agent: IntegratedAgent,
        template,
        dto: DirectSendCategoryDTO,
    ) -> None:
        self._emit(
            EventName.TEMPLATE_HAS_NO_CURRENT_VERSION,
            logging.WARNING,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            integrated_agent_uuid=integrated_agent.uuid,
            template_uuid=template.uuid,
        )

    def _emit_completed(
        self, dto: DirectSendCategoryDTO, result: DirectSendCategoryResult
    ) -> None:
        self._emit(
            EventName.COMPLETED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            templates_updated=result.templates_updated,
            integrated_agents_inspected=result.integrated_agents_inspected,
        )

    def _emit_unexpected_error(
        self, dto: DirectSendCategoryDTO, exc: Exception
    ) -> None:
        self._emit(
            EventName.UNEXPECTED_ERROR,
            logging.ERROR,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_name=dto.template_name,
            error=str(exc),
        )
