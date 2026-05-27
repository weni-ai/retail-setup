"""Direct Send sample-validation translator.

Pure-function module that turns a ``ValidateTemplateSampleDTO`` into
the Meta ``message_samples`` wire-shape dict. Reuses the Direct Send
broadcast renderer's ``substitute_template_variables`` so the outbound
sample matches what the eventual broadcast will render (US2 lockstep
guarantee). Anchor: FR-004 / FR-004a / FR-004b / FR-004c / FR-004e
(see ``specs/004-template-sample-validation/spec.md`` and
``contracts/meta-message-samples.md``).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from retail.agents.domains.agent_webhook.services.direct_send_payload_builder import (
    substitute_template_variables,
)
from retail.templates.adapters.url_normalization import (
    append_placeholder_if_needed,
    ensure_protocol,
)


if TYPE_CHECKING:
    from retail.templates.usecases.validate_template_sample import (
        ValidateTemplateSampleDTO,
    )


_REPLY_ID_NON_ALNUM = re.compile(r"[^a-z0-9]+")
_REPLY_ID_CONSECUTIVE_UNDERSCORE = re.compile(r"_+")
_REPLY_ID_MAX_LENGTH = 64

_URL_BUTTON_TYPE = "URL"
_QUICK_REPLY_BUTTON_TYPE = "QUICK_REPLY"

_IMAGE_HEADER_PROTOCOLS = ("http://", "https://")
_BASE64_DATA_URI_PREFIX = "data:"


def build_meta_sample_body(
    dto: "ValidateTemplateSampleDTO",
    *,
    resolved_header_url: Optional[str] = None,
) -> Dict[str, Any]:
    """Convert the DTO to the Meta ``message_samples`` wire shape.

    Substitution source is ``dto.template_body_params`` only;
    ``dto.parameters`` is intentionally not consulted (the rule-engine
    code-gen input is the wrong source for the outbound sample).
    Anchor: FR-004 / FR-004e / Decision 9.
    """
    template_name = dto.template_uuid
    variables = _variables_from_body_params(dto.template_body_params)

    substituted_body = _substitute(dto.template_body, variables, template_name)
    substituted_footer = _substitute(dto.template_footer, variables, template_name)

    buttons = dto.template_button or []
    url_buttons = [b for b in buttons if b.get("type") == _URL_BUTTON_TYPE]
    reply_buttons = [b for b in buttons if b.get("type") == _QUICK_REPLY_BUTTON_TYPE]

    if url_buttons:
        return _build_cta_url_shape(
            dto=dto,
            variables=variables,
            substituted_body=substituted_body,
            substituted_footer=substituted_footer,
            url_button=url_buttons[0],
            resolved_header_url=resolved_header_url,
            template_name=template_name,
        )

    if reply_buttons:
        return _build_reply_buttons_shape(
            dto=dto,
            variables=variables,
            substituted_body=substituted_body,
            substituted_footer=substituted_footer,
            reply_buttons=reply_buttons,
            resolved_header_url=resolved_header_url,
            template_name=template_name,
        )

    return _build_text_shape(
        dto=dto,
        variables=variables,
        substituted_body=substituted_body,
        substituted_footer=substituted_footer,
        resolved_header_url=resolved_header_url,
        template_name=template_name,
    )


def _variables_from_body_params(
    template_body_params: Optional[List[Any]],
) -> Dict[str, str]:
    """Build the positional-index -> value dict.

    Maps ``template_body_params[0]`` to ``"1"``, ``[1]`` to ``"2"``,
    etc. Anchor: Decision 9.
    """
    if not template_body_params:
        return {}
    return {
        str(index + 1): str(value) for index, value in enumerate(template_body_params)
    }


def _substitute(
    text: Optional[str], variables: Dict[str, str], template_name: str
) -> str:
    """Substitute ``{{N}}`` placeholders, returning the empty string on missing input."""
    if not text:
        return ""
    return substitute_template_variables(text, variables, template_name=template_name)


def _build_header_subobject(
    header: Optional[str],
    *,
    variables: Dict[str, str],
    resolved_header_url: Optional[str],
    template_name: str,
) -> Optional[Dict[str, Any]]:
    """Build the ``interactive.header`` value, or ``None`` when absent."""
    if not header:
        return None

    if _looks_like_image_header(header):
        link = resolved_header_url or header
        return {"type": "image", "image": {"link": link}}

    return {
        "type": "text",
        "text": _substitute(header, variables, template_name),
    }


def _looks_like_image_header(header: str) -> bool:
    """Return ``True`` when ``header`` is an HTTP(S) URL or base64 data URI."""
    if header.startswith(_IMAGE_HEADER_PROTOCOLS):
        return True
    if header.startswith(_BASE64_DATA_URI_PREFIX):
        return True
    return False


def _build_text_shape(
    *,
    dto: "ValidateTemplateSampleDTO",
    variables: Dict[str, str],
    substituted_body: str,
    substituted_footer: str,
    resolved_header_url: Optional[str],
    template_name: str,
) -> Dict[str, Any]:
    """Assemble the ``text`` wire body (Shape 1 / extended Shape 1b).

    Optional ``header`` / ``footer`` keys are absent (not ``null``) so
    the bare body-only case is byte-identical to Shape 1. Anchor: FR-004.
    """
    body: Dict[str, Any] = {"type": "text", "text": {"body": substituted_body}}

    header_subobject = _build_header_subobject(
        dto.template_header,
        variables=variables,
        resolved_header_url=resolved_header_url,
        template_name=template_name,
    )
    if header_subobject is not None:
        body["header"] = header_subobject

    if substituted_footer:
        body["footer"] = {"text": substituted_footer}

    return body


def _build_cta_url_shape(
    *,
    dto: "ValidateTemplateSampleDTO",
    variables: Dict[str, str],
    substituted_body: str,
    substituted_footer: str,
    url_button: Dict[str, Any],
    resolved_header_url: Optional[str],
    template_name: str,
) -> Dict[str, Any]:
    """Assemble the Shape 2 (``interactive.cta_url``) wire body."""
    interactive: Dict[str, Any] = {
        "type": "cta_url",
        "body": {"text": substituted_body},
        "action": {
            "name": "cta_url",
            "parameters": _build_cta_url_action_parameters(
                url_button=url_button,
                variables=variables,
                template_name=template_name,
            ),
        },
    }

    header_subobject = _build_header_subobject(
        dto.template_header,
        variables=variables,
        resolved_header_url=resolved_header_url,
        template_name=template_name,
    )
    if header_subobject is not None:
        interactive["header"] = header_subobject

    if substituted_footer:
        interactive["footer"] = {"text": substituted_footer}

    return {"type": "interactive", "interactive": interactive}


def _build_cta_url_action_parameters(
    *,
    url_button: Dict[str, Any],
    variables: Dict[str, str],
    template_name: str,
) -> Dict[str, str]:
    """Resolve the CTA URL button's ``{display_text, url}`` pair.

    Three accepted URL shapes (flat string, nested
    ``{base_url, url_suffix_example}``, nested ``{base_url}``) collapse
    to a canonical flat string before substitution, mirroring the
    broadcast renderer so sample and broadcast stay in lockstep.
    Anchor: FR-004b.
    """
    raw_url = url_button.get("url")
    resolved_url = _normalize_cta_url(raw_url)

    return {
        "display_text": _substitute(
            url_button.get("text", ""), variables, template_name
        ),
        "url": _substitute(resolved_url, variables, template_name),
    }


def _normalize_cta_url(raw_url: Any) -> str:
    """Collapse the three accepted CTA URL input shapes onto a canonical flat string."""
    if isinstance(raw_url, str):
        return raw_url

    if not isinstance(raw_url, dict):
        return ""

    base_url = ensure_protocol(raw_url.get("base_url") or "")
    if not base_url:
        return ""

    if "url_suffix_example" in raw_url:
        return append_placeholder_if_needed(base_url)

    return base_url


def _build_reply_buttons_shape(
    *,
    dto: "ValidateTemplateSampleDTO",
    variables: Dict[str, str],
    substituted_body: str,
    substituted_footer: str,
    reply_buttons: List[Dict[str, Any]],
    resolved_header_url: Optional[str],
    template_name: str,
) -> Dict[str, Any]:
    """Assemble the Shape 3 (``interactive.button``) wire body."""
    interactive: Dict[str, Any] = {
        "type": "button",
        "body": {"text": substituted_body},
        "action": {
            "buttons": _build_reply_button_entries(
                reply_buttons=reply_buttons,
                variables=variables,
                template_name=template_name,
            )
        },
    }

    header_subobject = _build_header_subobject(
        dto.template_header,
        variables=variables,
        resolved_header_url=resolved_header_url,
        template_name=template_name,
    )
    if header_subobject is not None:
        interactive["header"] = header_subobject

    if substituted_footer:
        interactive["footer"] = {"text": substituted_footer}

    return {"type": "interactive", "interactive": interactive}


def _build_reply_button_entries(
    *,
    reply_buttons: List[Dict[str, Any]],
    variables: Dict[str, str],
    template_name: str,
) -> List[Dict[str, Any]]:
    """Render reply buttons; duplicates get a ``_2``/``_3`` suffix. Anchor: FR-004c."""
    entries: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}

    for button in reply_buttons:
        title = _substitute(button.get("text", ""), variables, template_name)
        base_id = _derive_reply_id(button.get("text", ""))
        unique_id = _disambiguate_reply_id(base_id, seen_ids)

        entries.append({"type": "reply", "reply": {"id": unique_id, "title": title}})

    return entries


def _derive_reply_id(text: str) -> str:
    """Lowercase, non-alnum to ``_``, strip ``_``, truncate. Anchor: FR-004c."""
    if not text:
        return ""

    lowered = text.lower()
    underscored = _REPLY_ID_NON_ALNUM.sub("_", lowered)
    collapsed = _REPLY_ID_CONSECUTIVE_UNDERSCORE.sub("_", underscored)
    stripped = collapsed.strip("_")
    return stripped[:_REPLY_ID_MAX_LENGTH]


def _disambiguate_reply_id(base_id: str, seen_ids: Dict[str, int]) -> str:
    """Append ``_2`` / ``_3`` suffix on duplicate-within-payload."""
    if base_id not in seen_ids:
        seen_ids[base_id] = 1
        return base_id

    seen_ids[base_id] += 1
    return f"{base_id}_{seen_ids[base_id]}"
