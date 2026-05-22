"""Direct Send library-catalog fetch helpers.

Two helpers split per research Decision 9 / data-model.md §5:

- :func:`adapt_meta_library_template_response` — pure adapter shared
  between the legacy push-time validation flow
  (``ValidatePreApprovedTemplatesUseCase._get_template_info``) and the
  Direct Send-enabled assignment branch
  (``AssignAgentUseCase._create_library_templates``). Validates the
  raw library-catalog response against the Direct Send Beta supported
  set per ``contracts/meta-library-catalog.md`` §5 and raises
  :class:`DirectSendUnsupportedComponentError` on any violation
  (Decision 12).
- :func:`fetch_meta_library_template_metadata` — Direct-Send-only HTTP
  wrapper. Calls the service's exact-match fetch and delegates the
  response to :func:`adapt_meta_library_template_response`.

The split preserves Decision 4's "push-time keeps fuzzy semantics"
guarantee while extracting the response-shaping drift risk.
"""

from typing import Any, Dict, Optional, TypedDict

from retail.agents.domains.agent_integration.exceptions import (
    DirectSendUnsupportedComponentError,
)
from retail.agents.domains.agent_webhook.services.direct_send_constants import (
    MAX_BODY_LENGTH,
    MAX_BUTTON_LABEL_LENGTH,
    MAX_FOOTER_LENGTH,
    MAX_HEADER_TEXT_LENGTH,
)
from retail.interfaces.services.meta import MetaServiceInterface


class TemplateInfo(TypedDict):
    name: str
    content: str
    metadata: Dict[str, Any]


_SUPPORTED_HEADER_TYPES = {"TEXT", "IMAGE"}
_SUPPORTED_BUTTON_TYPES = {"URL", "QUICK_REPLY"}
_MAX_URL_BUTTONS = 1
_MAX_QUICK_REPLY_BUTTONS = 3


def adapt_meta_library_template_response(
    raw: Optional[Dict[str, Any]],
) -> Optional[TemplateInfo]:
    """Validate and shape a library-catalog response into ``TemplateInfo``.

    Returns ``None`` when ``raw is None``. Otherwise validates the
    components against the Direct Send Beta supported set
    (``contracts/meta-library-catalog.md`` §5) and shapes the response
    into the local ``Template.metadata`` form consumed by
    ``Broadcast.build_direct_send_message`` (data-model.md §3).
    Raises :class:`DirectSendUnsupportedComponentError` on any
    violation so the assignment use case rolls back atomically
    (Decision 12, FR-003d).
    """
    if raw is None:
        return None

    template_name = raw.get("name") or "<unknown>"

    _validate_components(raw, template_name=template_name)

    return {
        "name": raw.get("name"),
        "content": raw.get("body"),
        "metadata": {
            "header": _normalize_header(raw.get("header")),
            "body": raw.get("body"),
            "body_params": raw.get("body_params"),
            "footer": raw.get("footer"),
            "buttons": raw.get("buttons"),
            "category": raw.get("category"),
            "language": raw.get("language"),
        },
    }


def fetch_meta_library_template_metadata(
    meta_service: MetaServiceInterface,
    template_name: str,
    language: str,
) -> Optional[TemplateInfo]:
    """Fetch and adapt a library template via the Direct Send path.

    Calls
    :py:meth:`MetaServiceInterface.fetch_library_template_by_name_and_language`
    (exact-match) and delegates the response to
    :func:`adapt_meta_library_template_response`. The service swallows
    HTTP failures and returns ``None``; the adapter raises
    :class:`DirectSendUnsupportedComponentError` on validation
    violations.
    """
    raw = meta_service.fetch_library_template_by_name_and_language(
        template_name, language
    )
    return adapt_meta_library_template_response(raw)


def _validate_components(raw: Dict[str, Any], *, template_name: str) -> None:
    """Enforce contract §5 Direct Send Beta v1 supported-set rules."""
    body = raw.get("body")
    if not isinstance(body, str) or not body:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="body_missing_or_empty",
        )
    if len(body) > MAX_BODY_LENGTH:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type=f"body_length>{MAX_BODY_LENGTH}",
        )

    header = raw.get("header")
    if header is not None:
        header_type = header.get("type") if isinstance(header, dict) else None
        if header_type not in _SUPPORTED_HEADER_TYPES:
            raise DirectSendUnsupportedComponentError(
                template_name=template_name,
                component_type=f"header_type:{header_type}",
            )
        if header_type == "TEXT":
            header_text = header.get("text") or ""
            if len(header_text) > MAX_HEADER_TEXT_LENGTH:
                raise DirectSendUnsupportedComponentError(
                    template_name=template_name,
                    component_type=f"header_length>{MAX_HEADER_TEXT_LENGTH}",
                )

    footer = raw.get("footer")
    if footer is not None and len(footer) > MAX_FOOTER_LENGTH:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type=f"footer_length>{MAX_FOOTER_LENGTH}",
        )

    buttons = raw.get("buttons") or []
    url_count = 0
    quick_reply_count = 0
    for button in buttons:
        if not isinstance(button, dict):
            raise DirectSendUnsupportedComponentError(
                template_name=template_name,
                component_type="button_malformed",
            )
        btn_type = button.get("type")
        if btn_type not in _SUPPORTED_BUTTON_TYPES:
            raise DirectSendUnsupportedComponentError(
                template_name=template_name,
                component_type=f"button_type:{btn_type}",
            )
        if btn_type == "URL":
            url_count += 1
        else:
            quick_reply_count += 1

        label = button.get("text") or ""
        if len(label) > MAX_BUTTON_LABEL_LENGTH:
            raise DirectSendUnsupportedComponentError(
                template_name=template_name,
                component_type=f"button_label_length>{MAX_BUTTON_LABEL_LENGTH}",
            )

    if url_count > _MAX_URL_BUTTONS:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type=f"url_button_count>{_MAX_URL_BUTTONS}",
        )
    if quick_reply_count > _MAX_QUICK_REPLY_BUTTONS:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type=f"quick_reply_button_count>{_MAX_QUICK_REPLY_BUTTONS}",
        )


def _normalize_header(header: Any) -> Optional[Dict[str, Any]]:
    """Convert Meta's library-catalog header shape to Retail's internal one.

    Meta returns ``{"type": "TEXT", "text": "..."}`` or
    ``{"type": "IMAGE", "example": "..."}``; Retail's metadata stores
    ``{"header_type": "TEXT", "text": "..."}`` so
    ``Broadcast.build_direct_send_message`` and the existing
    ``HeaderTransformer`` "already translated" branch can read the
    same key. Returns ``None`` when the header is absent.

    Pre-condition: ``_validate_components`` has already enforced that
    ``header`` is either ``None`` or a dict whose ``type`` is in
    ``{"TEXT", "IMAGE"}``.
    """
    if not header:
        return None
    header_type = header["type"]
    if header_type == "TEXT":
        return {"header_type": "TEXT", "text": header.get("text", "")}
    return {"header_type": "IMAGE", "text": header.get("example", "")}
