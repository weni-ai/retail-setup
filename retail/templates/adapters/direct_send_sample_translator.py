"""Direct Send sample-validation translator.

Pure-function module that turns a ``ValidateTemplateSampleDTO`` into the
Meta ``message_samples`` wire-shape dict pinned by
``specs/004-template-sample-validation/contracts/meta-message-samples.md``.

Three discriminated shapes are produced:

- **Shape 1** ``text`` — body-only payload.
- **Shape 2** ``interactive.cta_url`` — exactly one ``URL``-type button.
- **Shape 3** ``interactive.button`` — 1–3 ``QUICK_REPLY`` buttons.

The function is pure: no DB access, no I/O, no Django imports. Callers
MUST resolve any base64 → S3 URL for IMAGE headers BEFORE invoking the
translator (the upload happens upstream in the use case per A9 /
Research Decision 6) and pass the resolved URL via ``resolved_header_url``.

The ``{{N}}`` placeholder substitution reuses
``substitute_template_variables`` from the Direct Send broadcast
renderer so the outbound sample matches what the eventual broadcast
will render (US2's lockstep guarantee per A7 / FR-004e).
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
    """Convert a validated sample-validation DTO to Meta's ``message_samples`` wire shape.

    Dispatches on the payload shape (body-only / URL button / reply
    buttons) per FR-004 / FR-004b / FR-004c, substitutes ``{{N}}``
    placeholders using ``dto.template_body_params`` as the positional
    substitution source (FR-004e / Research Decision 9 — ``dto.parameters``
    is NOT consulted), and emits the discriminated-union wire shape.

    Args:
        dto: Validated DTO with the operator-supplied content.
        resolved_header_url: For IMAGE-header payloads, the S3 URL the
            use case obtained by uploading the base64 blob upstream.
            Ignored on TEXT headers and on payloads without a header.

    Returns:
        Dict in the Meta ``message_samples`` wire shape (Shape 1, 2, or 3).
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

    return {"type": "text", "text": {"body": substituted_body}}


def _variables_from_body_params(
    template_body_params: Optional[List[Any]],
) -> Dict[str, str]:
    """Build the positional-index → value dict consumed by ``substitute_template_variables``.

    Maps ``template_body_params[0]`` → ``"1"``, ``[1]`` → ``"2"``, ...
    Research Decision 9 pins this as the SOLE substitution source for
    the outbound sample (the request body's ``parameters`` field —
    used by custom templates to feed the rule-engine code generator
    on the PATCH path — is a different input shape and is not
    consulted here).
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
    """Build the ``interactive.header`` discriminated-union value.

    Three modes per the header-shape table in ``contracts/meta-message-samples.md``:

    - TEXT header → ``{"type": "text", "text": "<substituted>"}``.
    - IMAGE header whose source was base64 → ``{"type": "image", "image": {"link": resolved_header_url}}``.
    - IMAGE header whose source was already an HTTP(S) URL → ``{"type": "image", "image": {"link": header}}``.

    Returns ``None`` for absent headers so callers can omit the key.
    """
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
    """Return ``True`` when ``header`` is an HTTP(S) URL or a base64 data URI.

    Mirrors the heuristic used by the existing ``HeaderTransformer`` /
    ``TemplateMetadataHandler`` so the wire-shape dispatch agrees with
    the local metadata persistence path.
    """
    if header.startswith(_IMAGE_HEADER_PROTOCOLS):
        return True
    if header.startswith(_BASE64_DATA_URI_PREFIX):
        return True
    return False


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
    """Resolve the CTA URL button's ``{display_text, url}`` pair per FR-004b.

    The URL field is accepted in three shapes (mirroring the existing
    ``UpdateLibraryTemplateButtonSerializer`` contract and the
    broadcast renderer's URL normalization at dispatch time, so the
    sample submitted to Meta stays in lockstep with what the eventual
    broadcast will render — see US2):

    - Already-flat string with the placeholder embedded
      (``"https://x/{{1}}"``) — preserved verbatim.
    - Nested ``{base_url, url_suffix_example}`` — normalized via
      ``ensure_protocol`` + ``append_placeholder_if_needed``.
    - Nested ``{base_url}`` only — ``ensure_protocol`` only, no
      placeholder appended.

    The placeholder substitution always fires last so the wire body
    carries the fully-resolved URL.
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
    """Render each reply button as ``{"type": "reply", "reply": {"id", "title"}}``.

    The ``reply.id`` is derived deterministically from the button text
    per FR-004c (see ``_derive_reply_id``) and tiebroken on
    duplicate-within-payload with a ``_2`` / ``_3`` positional suffix.
    """
    entries: List[Dict[str, Any]] = []
    seen_ids: Dict[str, int] = {}

    for button in reply_buttons:
        title = _substitute(button.get("text", ""), variables, template_name)
        base_id = _derive_reply_id(button.get("text", ""))
        unique_id = _disambiguate_reply_id(base_id, seen_ids)

        entries.append({"type": "reply", "reply": {"id": unique_id, "title": title}})

    return entries


def _derive_reply_id(text: str) -> str:
    """Derive a deterministic ``reply.id`` from a button label per FR-004c.

    Pipeline (matches ``contracts/meta-message-samples.md`` "Deterministic
    reply.id derivation"):

    1. Lowercase.
    2. Replace every non-alphanumeric run with a single underscore.
    3. Strip leading and trailing underscores.
    4. Truncate to ``_REPLY_ID_MAX_LENGTH`` (64) characters — well under
       WhatsApp's documented 256-char cap for ``reply.id``, leaving
       headroom for the duplicate-tiebreaker suffix and keeping
       audit-log lines tidy.
    """
    if not text:
        return ""

    lowered = text.lower()
    underscored = _REPLY_ID_NON_ALNUM.sub("_", lowered)
    collapsed = _REPLY_ID_CONSECUTIVE_UNDERSCORE.sub("_", underscored)
    stripped = collapsed.strip("_")
    return stripped[:_REPLY_ID_MAX_LENGTH]


def _disambiguate_reply_id(base_id: str, seen_ids: Dict[str, int]) -> str:
    """Append ``_2`` / ``_3`` suffix on duplicate-within-payload per FR-004c."""
    if base_id not in seen_ids:
        seen_ids[base_id] = 1
        return base_id

    seen_ids[base_id] += 1
    return f"{base_id}_{seen_ids[base_id]}"
