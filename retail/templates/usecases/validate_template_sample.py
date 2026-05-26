"""Validate-template-sample use case for the Direct Send pre-flight endpoint.

This module hosts both the in-memory data classes and the orchestration
behind ``POST /api/v3/templates/<uuid>/sample/`` (the feature pinned by
``specs/004-template-sample-validation/``).

The DTO is built by the view from
``ValidateTemplateSampleSerializer.validated_data``; the result is
shaped for ``Response(result.to_dict(), 200)`` per
``contracts/sample-endpoint-request-response.md``.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from rest_framework.exceptions import NotFound

from retail.clients.exceptions import CustomAPIException
from retail.interfaces.services.meta import MetaServiceInterface
from retail.templates.adapters.direct_send_sample_translator import (
    build_meta_sample_body,
)
from retail.templates.exceptions import (
    MetaInvalidResponseError,
    MetaSampleUnavailableError,
    NotDirectSendEligibleError,
    WabaNotConfiguredError,
)
from retail.templates.handlers import TemplateMetadataHandler
from retail.templates.models import Template
from retail.templates.strategies.update_template_strategies import (
    UpdateNormalTemplateStrategy,
)


logger = logging.getLogger(__name__)

LOG_TAG = "[TemplateSampleValidation]"


@dataclass(frozen=True)
class ValidateTemplateSampleDTO:
    """Validated, immutable payload passed from the view to the use case.

    Built by the view from ``ValidateTemplateSampleSerializer.validated_data``;
    consumed by ``ValidateTemplateSampleUseCase.execute(...)``. Carries the
    nine validated input fields enumerated in ``data-model.md`` §7 — the
    same field set the PATCH endpoint's ``UpdateTemplateContentSerializer``
    accepts today (FR-003 / FR-014 — schema parity is a hard guarantee
    so the frontend can call either endpoint with the same form state),
    plus the ``template_uuid`` path-param the sample endpoint receives
    on the URL.
    """

    template_uuid: str
    template_body: Optional[str]
    template_header: Optional[str]
    template_footer: Optional[str]
    template_button: Optional[List[Dict[str, Any]]]
    template_body_params: Optional[List[Any]]
    app_uuid: str
    project_uuid: str
    parameters: Optional[List[Dict[str, Any]]]
    language: Optional[str]


@dataclass(frozen=True)
class ValidateTemplateSampleResult:
    """Use-case return value shaped for the HTTP 200 response body.

    The view shapes the HTTP body as ``Response(result.to_dict(), 200)``.
    The wrapper exposes four top-level keys ``{category, template_updated,
    template, meta_sample_response}`` per FR-007 / FR-007a, with the
    ``template`` field serialized via the existing ``ReadTemplateSerializer``
    so the frontend can substitute it directly into its display state
    without re-fetching (SC-005).
    """

    category: str
    template_updated: bool
    template: Template
    meta_sample_response: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        from retail.templates.serializers import ReadTemplateSerializer

        return {
            "category": self.category,
            "template_updated": self.template_updated,
            "template": ReadTemplateSerializer(self.template).data,
            "meta_sample_response": self.meta_sample_response,
        }


class EventName(str, Enum):
    """Closed enumeration for the FR-008a ``event_name`` audit-log discriminator.

    Every audit-log entry from the sample-validation endpoint MUST carry
    exactly one of these tokens immediately after the
    ``[TemplateSampleValidation]`` tag. Additive-only — future PRs MAY
    add tokens but MUST NOT rename or remove existing ones (operator
    dashboards filter on these literal strings).
    """

    RECEIVED = "received"
    META_SAMPLE_SUBMITTED = "meta_sample_submitted"
    META_SAMPLE_RESPONSE = "meta_sample_response"
    TEMPLATE_UPDATED = "template_updated"
    UPDATE_SKIPPED = "update_skipped"
    META_ERROR = "meta_error"
    META_INVALID_RESPONSE = "meta_invalid_response"
    WABA_NOT_CONFIGURED = "waba_not_configured"
    NOT_DIRECT_SEND_ELIGIBLE = "not_direct_send_eligible"
    PROJECT_UUID_MISMATCH = "project_uuid_mismatch"
    LOCAL_UPDATE_FAILED_AFTER_META_APPROVAL = "local_update_failed_after_meta_approval"


class MetaSampleType(str, Enum):
    """The Meta ``message_samples`` interactive sub-type, for audit logging.

    Logged on the ``meta_sample_submitted`` event so dashboards can
    compute the per-template-type sample-mix (text vs CTA URL vs reply
    buttons) without re-parsing the request body. Pinned by
    ``data-model.md`` §7.
    """

    TEXT = "text"
    INTERACTIVE_CTA_URL = "interactive.cta_url"
    INTERACTIVE_BUTTON = "interactive.button"


class ValidateTemplateSampleUseCase:
    """Orchestrate the ``POST /api/v3/templates/<uuid>/sample/`` happy path.

    Loads the Template, gates on Direct-Send eligibility (FR-002a),
    resolves the project's WABA id (FR-005a), translates the validated
    DTO into Meta's ``message_samples`` wire shape (FR-004), submits the
    sample to Meta (FR-005), and conditionally writes a new APPROVED
    ``Version`` row + advances ``Template.current_version`` when Meta
    classifies the sample as ``UTILITY`` (FR-006 / FR-006a / FR-006d).
    Every observable step routes through ``_emit`` so the
    ``[TemplateSampleValidation]`` audit-log shape is enforced
    structurally (FR-008).

    The use case is framework-agnostic per Constitution Principle I —
    no rest_framework imports beyond the canonical ``NotFound`` raised
    by the template-load step, which DRF translates into HTTP 404 (per
    the legacy PATCH endpoint's precedent at
    ``retail/templates/usecases/update_template_body.py``). All other
    failure modes raise domain exceptions
    (``NotDirectSendEligibleError`` / ``WabaNotConfiguredError`` /
    ``MetaSampleUnavailableError`` / ``MetaInvalidResponseError``)
    that the view translates into HTTP 400 / 502 responses per FR-007.

    The serializer's FR-002b ``Project-Uuid`` header ↔ body
    ``project_uuid`` equality check runs upstream; the use case treats
    ``dto.project_uuid`` as the verified-trusted tenant identifier and
    does not re-check the header (single point of enforcement on the
    serializer layer per ``data-model.md`` §10).
    """

    _UTILITY_CATEGORY = "UTILITY"
    _DIRECT_SEND_CONFIG_KEY = "direct_send"
    _IMAGE_HEADER_PROTOCOLS = ("http://", "https://")
    _BASE64_DATA_URI_PREFIX = "data:"
    _APPROVED_VERSION_STATUS = "APPROVED"

    def __init__(
        self,
        meta_service: Optional[MetaServiceInterface] = None,
        strategy: Optional[UpdateNormalTemplateStrategy] = None,
        metadata_handler: Optional[TemplateMetadataHandler] = None,
    ):
        from retail.services.meta.service import MetaService

        self.meta_service = meta_service or MetaService()
        self.strategy = strategy or UpdateNormalTemplateStrategy()
        self.metadata_handler = metadata_handler or TemplateMetadataHandler()

    def execute(
        self, dto: ValidateTemplateSampleDTO
    ) -> ValidateTemplateSampleResult:
        self._emit_received(dto)

        template = self._load_template(dto.template_uuid)
        self._gate_on_direct_send_eligibility(template)
        waba_id = self._resolve_waba_id(dto.project_uuid)

        sample_body, sample_type = self._build_sample_body(dto)
        self._emit_meta_sample_submitted(dto, waba_id, sample_type)

        meta_response = self._call_meta_sample_api(dto, waba_id, sample_body)
        category = self._extract_category(meta_response)
        self._emit_meta_sample_response(dto, category, meta_response)

        template_updated = self._apply_local_update_on_utility(
            dto, template, category, meta_response
        )

        return ValidateTemplateSampleResult(
            category=category,
            template_updated=template_updated,
            template=template,
            meta_sample_response=meta_response,
        )

    def _load_template(self, template_uuid: str) -> Template:
        """Load the template by UUID with the integrated agent prefetched.

        ``select_related("integrated_agent")`` keeps the FR-002a gating
        predicate a pure in-memory check after this single read. Raises
        DRF's ``NotFound`` on miss so the view returns HTTP 404 (parity
        with the legacy PATCH endpoint per FR-011).
        """
        try:
            return Template.objects.select_related("integrated_agent").get(
                uuid=template_uuid
            )
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {template_uuid}")

    def _gate_on_direct_send_eligibility(self, template: Template) -> None:
        """FR-002a — refuse non-Direct-Send-eligible templates.

        Two failure modes (``data-model.md`` §4): the template has no
        ``IntegratedAgent`` FK (custom template never assigned), or the
        agent's ``config["direct_send"]`` flag is falsy. Both surface as
        a single ``NotDirectSendEligibleError`` distinguished only by
        the audit-log ``direct_send_flag`` / ``integrated_agent_uuid``
        fields so dashboards can split them at query time.
        """
        integrated_agent = template.integrated_agent
        direct_send_flag = (
            bool(integrated_agent.config.get(self._DIRECT_SEND_CONFIG_KEY))
            if integrated_agent
            else False
        )
        if direct_send_flag:
            return

        integrated_agent_uuid = integrated_agent.uuid if integrated_agent else None
        self._emit_not_direct_send_eligible(
            template, integrated_agent_uuid, direct_send_flag
        )
        raise NotDirectSendEligibleError(
            f"Template {template.uuid} is not Direct Send-eligible"
        )

    def _resolve_waba_id(self, project_uuid: str) -> str:
        """FR-005a — resolve the project's WABA id from onboarding config.

        Four failure modes collapse to a single ``WabaNotConfiguredError``
        (``data-model.md`` §3): missing ``ProjectOnboarding`` row,
        missing ``channels.wpp-cloud`` sub-config, missing
        ``channel_data.waba_id`` field, empty-string value. Operator
        observability is preserved by the ``waba_not_configured``
        audit-log event.
        """
        from retail.projects.models import ProjectOnboarding

        onboarding = ProjectOnboarding.objects.filter(
            project__uuid=project_uuid
        ).first()
        waba_id = self._extract_waba_id_from_onboarding(onboarding)
        if waba_id:
            return waba_id

        self._emit_waba_not_configured(project_uuid)
        raise WabaNotConfiguredError(
            f"WABA not configured for project {project_uuid}"
        )

    def _extract_waba_id_from_onboarding(self, onboarding) -> Optional[str]:
        if onboarding is None:
            return None
        channels = (onboarding.config or {}).get("channels") or {}
        wpp_cloud = channels.get("wpp-cloud") or {}
        channel_data = wpp_cloud.get("channel_data") or {}
        return channel_data.get("waba_id") or None

    def _build_sample_body(
        self, dto: ValidateTemplateSampleDTO
    ) -> tuple[Dict[str, Any], MetaSampleType]:
        """Translate the DTO into Meta's wire shape, uploading IMAGE base64 first.

        FR-004a / A9 — base64 IMAGE headers MUST be uploaded to S3
        before the Meta call so the wire body carries a public URL and
        the downstream metadata persistence (which calls
        ``post_process_translation``) sees an already-resolved S3 URL
        and skips a redundant re-upload (per ``TemplateMetadataHandler._is_s3_url``).
        """
        resolved_header_url = self._resolve_header_image_url(dto.template_header)
        sample_body = build_meta_sample_body(
            dto, resolved_header_url=resolved_header_url
        )
        sample_type = self._infer_sample_type(sample_body)
        return sample_body, sample_type

    def _resolve_header_image_url(self, header: Optional[str]) -> Optional[str]:
        if not header:
            return None
        if header.startswith(self._IMAGE_HEADER_PROTOCOLS):
            return header
        if header.startswith(self._BASE64_DATA_URI_PREFIX):
            return self.metadata_handler._upload_header_image({"text": header})
        return None

    def _infer_sample_type(self, sample_body: Dict[str, Any]) -> MetaSampleType:
        if sample_body.get("type") == "text":
            return MetaSampleType.TEXT
        interactive_type = (sample_body.get("interactive") or {}).get("type")
        if interactive_type == "cta_url":
            return MetaSampleType.INTERACTIVE_CTA_URL
        return MetaSampleType.INTERACTIVE_BUTTON

    def _call_meta_sample_api(
        self,
        dto: ValidateTemplateSampleDTO,
        waba_id: str,
        sample_body: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call Meta's ``message_samples`` endpoint and translate failures.

        ``MetaService.submit_template_sample`` propagates exceptions
        unmodified per FR-005c / Research Decision 5; this method is
        the single point that catches them and raises the domain
        ``MetaSampleUnavailableError`` so the view's exception-translation
        block stays clean.
        """
        try:
            return self.meta_service.submit_template_sample(waba_id, sample_body)
        except CustomAPIException as exc:
            self._emit_meta_error(dto, waba_id, exc)
            raise MetaSampleUnavailableError(
                f"Meta sample submission failed for template {dto.template_uuid}",
                status_code=getattr(exc, "status_code", None),
                meta_response=self._extract_meta_response_from_exception(exc),
            ) from exc
        except Exception as exc:
            self._emit_meta_error(dto, waba_id, exc)
            raise MetaSampleUnavailableError(
                f"Meta sample submission failed for template {dto.template_uuid}",
            ) from exc

    def _extract_meta_response_from_exception(
        self, exc: CustomAPIException
    ) -> Optional[Dict[str, Any]]:
        detail = getattr(exc, "detail", None)
        if isinstance(detail, dict):
            return detail
        return None

    def _extract_category(self, meta_response: Dict[str, Any]) -> str:
        """Validate Meta's response carries a usable ``category`` field.

        Four invalid shapes collapse to ``MetaInvalidResponseError``
        (FR-005b / FR-005c): ``success`` is explicitly ``false``; the
        ``category`` key is missing; the ``category`` value is empty;
        the value is non-string. The exception carries the raw Meta
        body so the view surfaces it on the HTTP 502 response.
        """
        success = meta_response.get("success", True)
        category = meta_response.get("category")

        is_invalid = (
            success is False
            or not category
            or not isinstance(category, str)
        )
        if is_invalid:
            self._emit_meta_invalid_response(meta_response)
            raise MetaInvalidResponseError(
                "Meta did not return a category",
                meta_response=meta_response,
            )

        return category

    def _apply_local_update_on_utility(
        self,
        dto: ValidateTemplateSampleDTO,
        template: Template,
        category: str,
        meta_response: Dict[str, Any],
    ) -> bool:
        """Conditionally rewrite local state when Meta classifies as UTILITY.

        On non-UTILITY (FR-005b / FR-006b) the local template is
        untouched and ``update_skipped`` is emitted. On UTILITY
        (FR-006 / FR-006a / FR-006d) the strategy's metadata helper
        is composed with the APPROVED-version helper to perform the
        four mandatory writes (data-model.md §9). Any exception in
        the local-update half re-raises after emitting
        ``local_update_failed_after_meta_approval`` at ERROR level
        with ``exc_info=True`` (FR-006c / FR-008b).
        """
        if category != self._UTILITY_CATEGORY:
            self._emit_update_skipped(dto, template, category)
            return False

        previous_version = template.current_version
        previous_current_version_uuid = (
            previous_version.uuid if previous_version else None
        )
        previous_current_version_status = (
            previous_version.status if previous_version else None
        )

        try:
            payload = self._strategy_payload(dto)
            self.strategy._build_and_persist_metadata(template, payload)
            new_version = self.strategy._create_approved_current_version(
                template, payload
            )
        except Exception as exc:
            self._emit_local_update_failed_after_meta_approval(
                dto, template, meta_response, exc
            )
            raise

        template.refresh_from_db()
        self._emit_template_updated(
            dto,
            template,
            new_version,
            previous_current_version_uuid,
            previous_current_version_status,
        )
        return True

    def _strategy_payload(
        self, dto: ValidateTemplateSampleDTO
    ) -> Dict[str, Any]:
        """Materialize the strategy's dict-style payload from the DTO.

        The strategy interface predates the DTO (it is shared with the
        legacy PATCH path) and expects a plain dict; this adapter keeps
        the strategy layer unchanged and isolated from the new endpoint's
        DTO shape.
        """
        return {
            "template_body": dto.template_body,
            "template_header": dto.template_header,
            "template_footer": dto.template_footer,
            "template_button": dto.template_button,
            "template_body_params": dto.template_body_params,
            "app_uuid": dto.app_uuid,
            "project_uuid": dto.project_uuid,
            "parameters": dto.parameters,
            "language": dto.language,
        }

    def _emit(self, event: EventName, level: int, **kv) -> None:
        """Single emission point that knows the FR-008 log-line shape.

        Every audit-log entry for this endpoint MUST route through this
        method — the ``[TemplateSampleValidation]`` tag, the
        ``event_name: k=v ...`` shape, and the log-level discipline are
        enforced structurally here so callers cannot drift from FR-008.

        Customer-facing content (body, header, footer, button text) is
        PII-redacted by callers BEFORE invocation per FR-008c — they
        pass length / presence flags. Identifiers (UUIDs) are passed
        verbatim per the same FR's carve-out.
        """
        payload = " ".join(f"{key}={value}" for key, value in kv.items())
        message = f"{LOG_TAG} {event.value}: {payload}".replace("%", "%%")
        if level == logging.ERROR:
            logger.error(message, kv, exc_info=True)
        elif level == logging.WARNING:
            logger.warning(message, kv)
        else:
            logger.info(message, kv)

    def _emit_received(self, dto: ValidateTemplateSampleDTO) -> None:
        self._emit(
            EventName.RECEIVED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            app_uuid=dto.app_uuid,
            template_uuid=dto.template_uuid,
            template_body_len=len(dto.template_body or ""),
            template_header_present=bool(dto.template_header),
            template_footer_present=bool(dto.template_footer),
            buttons_count=len(dto.template_button or []),
        )

    def _emit_meta_sample_submitted(
        self,
        dto: ValidateTemplateSampleDTO,
        waba_id: str,
        sample_type: MetaSampleType,
    ) -> None:
        self._emit(
            EventName.META_SAMPLE_SUBMITTED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            template_uuid=dto.template_uuid,
            waba_id=waba_id,
            sample_type=sample_type.value,
        )

    def _emit_meta_sample_response(
        self,
        dto: ValidateTemplateSampleDTO,
        category: str,
        meta_response: Dict[str, Any],
    ) -> None:
        self._emit(
            EventName.META_SAMPLE_RESPONSE,
            logging.INFO,
            project_uuid=dto.project_uuid,
            template_uuid=dto.template_uuid,
            category=category,
            success=meta_response.get("success", True),
        )

    def _emit_template_updated(
        self,
        dto: ValidateTemplateSampleDTO,
        template: Template,
        new_version,
        previous_current_version_uuid,
        previous_current_version_status: Optional[str],
    ) -> None:
        self._emit(
            EventName.TEMPLATE_UPDATED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            template_uuid=template.uuid,
            new_version_uuid=new_version.uuid,
            new_version_status=new_version.status,
            previous_current_version_uuid=previous_current_version_uuid,
            previous_current_version_status=previous_current_version_status,
        )

    def _emit_update_skipped(
        self,
        dto: ValidateTemplateSampleDTO,
        template: Template,
        category: str,
    ) -> None:
        self._emit(
            EventName.UPDATE_SKIPPED,
            logging.INFO,
            project_uuid=dto.project_uuid,
            template_uuid=template.uuid,
            category=category,
        )

    def _emit_meta_error(
        self,
        dto: ValidateTemplateSampleDTO,
        waba_id: str,
        exc: Exception,
    ) -> None:
        self._emit(
            EventName.META_ERROR,
            logging.ERROR,
            project_uuid=dto.project_uuid,
            template_uuid=dto.template_uuid,
            waba_id=waba_id,
            status_code=getattr(exc, "status_code", None),
            error=str(exc),
        )

    def _emit_meta_invalid_response(self, meta_response: Dict[str, Any]) -> None:
        self._emit(
            EventName.META_INVALID_RESPONSE,
            logging.WARNING,
            meta_response=meta_response,
        )

    def _emit_waba_not_configured(self, project_uuid: str) -> None:
        self._emit(
            EventName.WABA_NOT_CONFIGURED,
            logging.WARNING,
            project_uuid=project_uuid,
        )

    def _emit_not_direct_send_eligible(
        self,
        template: Template,
        integrated_agent_uuid,
        direct_send_flag: bool,
    ) -> None:
        self._emit(
            EventName.NOT_DIRECT_SEND_ELIGIBLE,
            logging.WARNING,
            template_uuid=template.uuid,
            integrated_agent_uuid=integrated_agent_uuid,
            direct_send_flag=direct_send_flag,
        )

    def _emit_local_update_failed_after_meta_approval(
        self,
        dto: ValidateTemplateSampleDTO,
        template: Template,
        meta_response: Dict[str, Any],
        exc: Exception,
    ) -> None:
        self._emit(
            EventName.LOCAL_UPDATE_FAILED_AFTER_META_APPROVAL,
            logging.ERROR,
            project_uuid=dto.project_uuid,
            template_uuid=template.uuid,
            meta_sample_id=meta_response.get("id"),
            error=str(exc),
        )
