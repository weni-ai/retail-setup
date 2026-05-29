"""Direct Send library-catalog fetch + adaptation helpers.

Validates raw library-catalog responses against the Direct Send Beta
supported set and shapes them into the local ``Template.metadata``
form. Anchor: FR-003c / FR-003d / FR-003e / FR-003f / FR-003g /
Research Decision 9 / Decision 12 (see
``specs/002-direct-send-broadcasts/spec.md`` and
``contracts/meta-library-catalog.md`` §5).
"""

import logging

from typing import Any, Dict, List, Optional, TypedDict

from retail.agents.domains.agent_integration.exceptions import (
    DirectSendUnsupportedComponentError,
)
from retail.agents.domains.agent_webhook.services import (
    direct_send_button_overrides,
)
from retail.agents.domains.agent_webhook.services.direct_send_constants import (
    MAX_BODY_LENGTH,
    MAX_BUTTON_LABEL_LENGTH,
    MAX_FOOTER_LENGTH,
    MAX_HEADER_TEXT_LENGTH,
)
from retail.interfaces.services.meta import MetaServiceInterface
from retail.templates.adapters.url_normalization import (
    append_placeholder_if_needed,
    ensure_protocol,
)

logger = logging.getLogger(__name__)


class TemplateInfo(TypedDict):
    name: str
    content: str
    metadata: Dict[str, Any]


_SUPPORTED_BUTTON_TYPES = {"URL", "QUICK_REPLY"}
_MAX_URL_BUTTONS = 1
_MAX_QUICK_REPLY_BUTTONS = 3
_OVERRIDE_FALLBACK_LANGUAGE = "pt_BR"


def adapt_meta_library_template_response(
    raw: Optional[Dict[str, Any]],
    language: Optional[str] = None,
) -> Optional[TemplateInfo]:
    """Validate and shape a library-catalog response into ``TemplateInfo``.

    Returns ``None`` when ``raw is None``; raises
    :class:`DirectSendUnsupportedComponentError` on any unsupported
    component. ``language`` is consulted for the FR-003g URL-button
    label override; ``None`` keeps the legacy push-path source-compat.
    Anchor: FR-003c / FR-003d / FR-003g / Decision 12.
    """
    if raw is None:
        return None

    template_name = raw.get("name") or "<unknown>"

    body = _validate_body(raw, template_name=template_name)
    header = _validate_and_normalize_header(raw, template_name=template_name)
    footer = _validate_footer(raw, template_name=template_name)
    buttons = _validate_and_normalize_buttons(
        raw, template_name=template_name, language=language
    )

    return {
        "name": raw.get("name"),
        "content": body,
        "metadata": {
            "header": header,
            "body": body,
            "body_params": raw.get("body_params"),
            "footer": footer,
            "buttons": buttons,
            "category": raw.get("category"),
            "language": raw.get("language"),
        },
    }


def fetch_meta_library_template_metadata(
    meta_service: MetaServiceInterface,
    template_name: str,
    language: str,
) -> Optional[TemplateInfo]:
    """Exact-match Direct Send library fetch + adapt.

    HTTP failures surface as ``None``; adapter rejections raise
    :class:`DirectSendUnsupportedComponentError`.
    """
    raw = meta_service.fetch_library_template_by_name_and_language(
        template_name, language
    )
    return adapt_meta_library_template_response(raw, language=language)


def _validate_body(raw: Dict[str, Any], *, template_name: str) -> str:
    body = raw.get("body")
    if not isinstance(body, str) or not body:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="malformed",
        )
    if len(body) > MAX_BODY_LENGTH:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="body",
        )
    return body


def _validate_and_normalize_header(
    raw: Dict[str, Any], *, template_name: str
) -> Optional[Dict[str, Any]]:
    """Normalize Meta's plain-string ``header`` to ``{header_type, text}``.

    Anchor: FR-003e (any non-null, non-string shape is malformed).
    """
    header = raw.get("header")
    if header is None:
        return None
    if not isinstance(header, str):
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="header",
        )
    if len(header) > MAX_HEADER_TEXT_LENGTH:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="header",
        )
    return {"header_type": "TEXT", "text": header}


def _validate_footer(raw: Dict[str, Any], *, template_name: str) -> Optional[str]:
    footer = raw.get("footer")
    if footer is None:
        return None
    if not isinstance(footer, str) or len(footer) > MAX_FOOTER_LENGTH:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="footer",
        )
    return footer


def _validate_and_normalize_buttons(
    raw: Dict[str, Any],
    *,
    template_name: str,
    language: Optional[str] = None,
) -> Optional[List[Dict[str, Any]]]:
    """Validate types and normalize URL-button shapes.

    Anchor: FR-003f (type allowlist + dual URL-shape normalization
    shared with the push-path ``ButtonTransformer``) / FR-003g
    (URL-button label override on overflow).
    """
    raw_buttons = raw.get("buttons")
    if raw_buttons is None:
        return None

    normalized: List[Dict[str, Any]] = []
    url_count = 0
    quick_reply_count = 0

    for button in raw_buttons:
        if not isinstance(button, dict):
            raise DirectSendUnsupportedComponentError(
                template_name=template_name,
                component_type="malformed",
            )

        btn_type = button.get("type")
        if btn_type not in _SUPPORTED_BUTTON_TYPES:
            raise DirectSendUnsupportedComponentError(
                template_name=template_name,
                component_type=btn_type if isinstance(btn_type, str) else "malformed",
            )

        label = button.get("text") or ""
        if len(label) > MAX_BUTTON_LABEL_LENGTH:
            if btn_type == "URL":
                label = _resolve_url_button_label_override(
                    upstream=label,
                    template_name=template_name,
                    language=language,
                )
            else:
                raise DirectSendUnsupportedComponentError(
                    template_name=template_name,
                    component_type="buttons",
                )

        if btn_type == "URL":
            url_count += 1
            normalized.append(
                {
                    "type": "URL",
                    "text": label,
                    "url": _flatten_url(button.get("url"), template_name=template_name),
                }
            )
        else:
            quick_reply_count += 1
            normalized.append({"type": "QUICK_REPLY", "text": label})

    if url_count > _MAX_URL_BUTTONS or quick_reply_count > _MAX_QUICK_REPLY_BUTTONS:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="buttons",
        )

    return normalized


def _resolve_url_button_label_override(
    *,
    upstream: str,
    template_name: str,
    language: Optional[str],
) -> str:
    """Look up the URL-button label override for ``(template_name, language)``,
    falling back to the ``pt_BR`` entry when the requested language is unmapped.

    Caller has already confirmed the upstream overflow. A missing override
    (in both the requested language and the ``pt_BR`` fallback) or one that
    itself overflows raises (the map is a remediation, not a length-check
    bypass). Anchor: FR-003g(c) / FR-003g(f) / FR-003g(h).
    """
    override_map = direct_send_button_overrides.DIRECT_SEND_BUTTON_LABEL_OVERRIDES
    override = override_map.get((template_name, language))
    if override is None:
        override = override_map.get((template_name, _OVERRIDE_FALLBACK_LANGUAGE))

    if override is None or len(override) > MAX_BUTTON_LABEL_LENGTH:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="buttons",
        )

    logger.info(
        f"direct_send_button_label_overridden: "
        f"template={template_name} language={language} "
        f"upstream='{upstream}' ({len(upstream)} chars) "
        f"override='{override}' ({len(override)} chars)"
    )
    return override


def _flatten_url(url: Any, *, template_name: str) -> str:
    """Collapse flat-string and nested-dict URL shapes onto a flat string."""
    if isinstance(url, str):
        return ensure_protocol(url)
    if isinstance(url, dict) and isinstance(url.get("base_url"), str):
        base = ensure_protocol(url["base_url"])
        if "url_suffix_example" in url:
            return append_placeholder_if_needed(base)
        return base
    raise DirectSendUnsupportedComponentError(
        template_name=template_name,
        component_type="malformed",
    )
