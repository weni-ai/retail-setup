"""Validate-template-sample use case for the Direct Send pre-flight endpoint.

Anchor: ``specs/004-template-sample-validation/spec.md``.
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from rest_framework.exceptions import NotFound

from retail.clients.exceptions import CustomAPIException
from retail.interfaces.services.integrations import IntegrationsServiceInterface
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

    Field set is schema-parallel with the PATCH endpoint's
    ``UpdateTemplateContentSerializer`` plus the ``template_uuid``
    path-param. Anchor: FR-003 / FR-014.
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
    """HTTP 200 response body shape ``{category, template_updated,
    template, meta_sample_response}``. Anchor: FR-007 / FR-007a / SC-005.
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
    """Closed audit-log ``event_name`` discriminator. Anchor: FR-008a (additive-only)."""

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
    """Meta ``message_samples`` interactive sub-type for audit logging."""

    TEXT = "text"
    INTERACTIVE_CTA_URL = "interactive.cta_url"
    INTERACTIVE_BUTTON = "interactive.button"


class ValidateTemplateSampleUseCase:
    """Orchestrate the ``POST /api/v3/templates/<uuid>/sample/`` flow.

    Framework-agnostic except for DRF's ``NotFound`` on the
    template-load miss (HTTP 404 parity with the legacy PATCH
    endpoint). Domain failures raise dedicated exceptions translated
    to HTTP 400/502 by the view. Anchor: FR-002a / FR-004 / FR-005
    / FR-005a / FR-006 / FR-007 / FR-008 (see
    ``specs/004-template-sample-validation/spec.md``).
    """

    _UTILITY_CATEGORY = "UTILITY"
    _DIRECT_SEND_CONFIG_KEY = "direct_send"
    _IMAGE_HEADER_PROTOCOLS = ("http://", "https://")
    _BASE64_DATA_URI_PREFIX = "data:"
    _APPROVED_VERSION_STATUS = "APPROVED"
    _WPP_CLOUD_APPTYPE = "wpp-cloud"

    def __init__(
        self,
        meta_service: Optional[MetaServiceInterface] = None,
        strategy: Optional[UpdateNormalTemplateStrategy] = None,
        metadata_handler: Optional[TemplateMetadataHandler] = None,
        integrations_service: Optional[IntegrationsServiceInterface] = None,
    ):
        from retail.services.integrations.service import IntegrationsService
        from retail.services.meta.service import MetaService

        self.meta_service = meta_service or MetaService()
        self.strategy = strategy or UpdateNormalTemplateStrategy()
        self.metadata_handler = metadata_handler or TemplateMetadataHandler()
        self.integrations_service = integrations_service or IntegrationsService()

    def execute(
        self, dto: ValidateTemplateSampleDTO
    ) -> ValidateTemplateSampleResult:
        self._emit_received(dto)

        template = self._load_template(dto.template_uuid)
        self._gate_on_direct_send_eligibility(template)
        waba_id = self._resolve_waba_id(dto.project_uuid, dto.app_uuid)

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
        """Load the template with the integrated agent prefetched.

        Raises ``NotFound`` on miss -> HTTP 404. Anchor: FR-011.
        """
        try:
            return Template.objects.select_related("integrated_agent").get(
                uuid=template_uuid
            )
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {template_uuid}")

    def _gate_on_direct_send_eligibility(self, template: Template) -> None:
        """Refuse non-Direct-Send-eligible templates. Anchor: FR-002a."""
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

    def _resolve_waba_id(self, project_uuid: str, app_uuid: str) -> str:
        """Resolve the project's WABA id via integrations.

        Three failure modes collapse to ``WabaNotConfiguredError``,
        distinguishable via the ``integrations_response_present``
        audit-log flag. Anchor: FR-005a.
        """
        app = self.integrations_service.get_channel_app(
            self._WPP_CLOUD_APPTYPE, app_uuid
        )
        waba_id = ((app or {}).get("config") or {}).get("waba", {}).get("id")
        if waba_id:
            return waba_id

        self._emit_waba_not_configured(
            project_uuid, app_uuid, integrations_response_present=bool(app)
        )
        raise WabaNotConfiguredError(
            f"WABA not configured for project {project_uuid}"
        )

    def _build_sample_body(
        self, dto: ValidateTemplateSampleDTO
    ) -> tuple[Dict[str, Any], MetaSampleType]:
        """Translate the DTO into Meta's wire shape.

        Base64 IMAGE headers are uploaded to S3 upfront so the
        downstream metadata persistence sees an already-resolved S3
        URL and skips a redundant re-upload. Anchor: FR-004a.
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

        Single point that maps upstream exceptions to
        ``MetaSampleUnavailableError``. Anchor: FR-005c / Decision 5.
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
        """Validate Meta returned a usable string ``category``.

        Four invalid shapes (false success, missing/empty/non-string
        category) collapse to ``MetaInvalidResponseError``. Anchor:
        FR-005b / FR-005c.
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
        """Rewrite local state only on Meta UTILITY classification.

        Anchor: FR-006 / FR-006a / FR-006c / FR-006d / FR-008b.
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
        """Materialize the legacy strategy's dict-style payload from the DTO."""
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
        """Single emission point for the audit log-line shape.

        Callers MUST pass length / presence flags for customer-facing
        content (PII redaction). Anchor: FR-008 / FR-008c.
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

    def _emit_waba_not_configured(
        self,
        project_uuid: str,
        app_uuid: str,
        integrations_response_present: bool,
    ) -> None:
        self._emit(
            EventName.WABA_NOT_CONFIGURED,
            logging.WARNING,
            project_uuid=project_uuid,
            app_uuid=app_uuid,
            integrations_response_present=integrations_response_present,
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
