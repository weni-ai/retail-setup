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

The four rejection branches (header shape, button type, length/count
overflow, malformed JSON) collapse to a single exception class
(``DirectSendUnsupportedComponentError``) so the use case keeps a
single FR-003c → FR-003d routing path. ``component_type`` carries a
stable discriminator:

- ``"header"`` — header shape OR header length issues (FR-003e)
- ``"<button.type>"`` — specific button type outside ``{URL, QUICK_REPLY}``
  (FR-003f); e.g. ``"PHONE_NUMBER"``, ``"PAYMENT_REQUEST"``,
  ``"ORDER_DETAILS"``, ``"COPY_CODE"``, ``"FLOW"``
- ``"body"`` / ``"footer"`` / ``"buttons"`` — length or count overflow
  on a known component
- ``"malformed"`` — missing required keys, structural violations
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


def adapt_meta_library_template_response(
    raw: Optional[Dict[str, Any]],
    language: Optional[str] = None,
) -> Optional[TemplateInfo]:
    """Validate and shape a library-catalog response into ``TemplateInfo``.

    Returns ``None`` when ``raw is None``. Otherwise validates the
    components against the Direct Send Beta supported set
    (``contracts/meta-library-catalog.md`` §5) and shapes the response
    into the local ``Template.metadata`` form consumed by
    ``Broadcast.build_direct_send_message`` (data-model.md §3).
    Raises :class:`DirectSendUnsupportedComponentError` on any
    violation so the assignment use case routes through FR-003c →
    FR-003d (Decision 12).

    ``language`` is the locale the Direct Send fetch is occurring in
    (project locale or ``pt_BR`` fallback). When provided AND a URL
    button's text would overflow ``MAX_BUTTON_LABEL_LENGTH``, the
    per-``(template_name, language)`` override map is consulted to
    remediate the overflow (FR-003g). Defaults to ``None`` so the
    legacy push-time validation flow remains source-compatible.
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
    """Normalize Meta's plain-string ``header`` to the canonical shape.

    FR-003e: Meta's library catalog ALWAYS returns ``header`` either
    absent or as a plain text string. Any non-string, non-null shape
    (including the pre-FR-003e dict ``{type, text}``) is treated as
    malformed and raises ``DirectSendUnsupportedComponentError(
    component_type="header")`` so the use case routes through
    FR-003c → FR-003d. Plain-string headers are length-validated
    against ``MAX_HEADER_TEXT_LENGTH`` and normalized to the
    canonical Retail-internal shape ``{header_type: "TEXT",
    text: <string>}`` (data-model.md §3).
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

    FR-003f: ``buttons[*].type`` outside ``{URL, QUICK_REPLY}`` raises
    ``DirectSendUnsupportedComponentError(component_type=<type>)``;
    URL-button entries accept either a flat ``url`` string OR the
    legacy nested ``{base_url, url_suffix_example}`` shape and are
    normalized to a single flat-string canonical form via the shared
    ``ensure_protocol`` + ``append_placeholder_if_needed`` helpers
    (push-path ``ButtonTransformer`` agrees on the same heuristic).

    FR-003g: when a URL button's text would otherwise overflow
    ``MAX_BUTTON_LABEL_LENGTH`` AND a ``(template_name, language)``
    entry exists in ``DIRECT_SEND_BUTTON_LABEL_OVERRIDES``, the
    override value replaces the upstream label and the length check
    is re-run. QUICK_REPLY overflows continue to raise.
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
    """Look up the URL button label override for ``(template_name, language)``.

    The override is applied ONLY when the upstream label overflowed
    ``MAX_BUTTON_LABEL_LENGTH`` (the caller has already confirmed the
    overflow). Per FR-003g(h) the override value itself MUST satisfy
    the same length ceiling; an override that overflows raises
    ``DirectSendUnsupportedComponentError`` (the map is a remediation,
    not a length-check bypass). Per FR-003g(f) audit is INFO-log-only.
    """
    override_key = (template_name, language)
    override_map = direct_send_button_overrides.DIRECT_SEND_BUTTON_LABEL_OVERRIDES
    if language is None or override_key not in override_map:
        raise DirectSendUnsupportedComponentError(
            template_name=template_name,
            component_type="buttons",
        )

    override = override_map[override_key]
    if len(override) > MAX_BUTTON_LABEL_LENGTH:
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
    """Collapse the two upstream URL shapes onto a flat string.

    - Flat string: ensure protocol, preserve placeholders verbatim.
    - Nested ``{base_url, url_suffix_example}``: ensure protocol on
      ``base_url`` and append ``{{1}}`` when ``url_suffix_example``
      signals a parameterizable suffix.
    """
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
