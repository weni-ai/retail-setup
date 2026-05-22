"""Direct Send payload-building helpers.

Pure functions used by ``Broadcast.build_direct_send_message`` to
turn a Direct Send-enabled ``Template.metadata`` + Lambda
``template_variables`` into the wire shape pinned by
``contracts/messaging-gateway-payload.md`` §3.

Two responsibilities:

- ``substitute_template_variables`` — substitute ``{{N}}`` placeholders
  (whitespace-tolerant) with values from a positional dict (research
  Decision 6). Missing indices log a WARNING and substitute to empty
  string; extra indices are silently ignored.
- ``is_valid_direct_send_template_name`` — enforce Meta's Direct Send
  Beta identifier rule (snake_case + ≤ 512 chars, research Decision 7
  / FR-017).

The header / footer / cta / quick_replies builders consume the
``Template.metadata`` shape produced by ``_get_template_info`` /
``adapt_meta_library_template_response`` (data-model.md §3).

FR-014a / FR-014b wire shape (Session 2026-05-22 Q4 / Q10) — the
Direct Send path NEVER emits ``msg.buttons`` (LEGACY-ONLY):

- CTA URL → ``msg.interaction_type = "cta_url"`` +
  ``msg.cta_message = {display_text, url}`` siblings on ``msg``.
- QUICK_REPLY → flat ``msg.quick_replies = ["title 1", ...]`` array.
"""

import logging
import re

from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_VARIABLE_RE = re.compile(r"\{\{\s*(\d+)\s*\}\}")
_TEMPLATE_NAME_RE = re.compile(r"^[a-z0-9_]+$")
_MAX_TEMPLATE_NAME_LENGTH = 512


def substitute_template_variables(
    text: str,
    variables: Dict[str, Any],
    *,
    template_name: str,
) -> str:
    """Replace every ``{{N}}`` placeholder with ``str(variables[str(N)])``.

    Missing indices substitute to empty string and emit a WARNING log
    so operators can detect the rule-engine gap without halting the
    broadcast. Extra indices in ``variables`` are silently ignored
    (research Decision 6 + spec edge cases).
    """
    if not text:
        return text

    def _replace(match: re.Match) -> str:
        index = match.group(1)
        if index in variables:
            return str(variables[index])
        logger.warning(
            f"[DirectSend] variable_missing: " f"template={template_name} index={index}"
        )
        return ""

    return _VARIABLE_RE.sub(_replace, text)


def is_valid_direct_send_template_name(name: str) -> bool:
    """Return True iff ``name`` satisfies Meta's Direct Send identifier rule.

    The rule is ``^[a-z0-9_]+$`` with length ≤ 512 (research
    Decision 7, FR-017). Names that fail this check MUST NOT be sent
    through Direct Send; the dispatcher refuses to emit a payload.
    """
    if not name or len(name) > _MAX_TEMPLATE_NAME_LENGTH:
        return False
    return bool(_TEMPLATE_NAME_RE.match(name))


def build_direct_send_header(
    metadata: Dict[str, Any],
    template_variables: Dict[str, Any],
    *,
    template_name: str,
    image_url: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Build the ``msg.header`` sub-object for the Direct Send payload.

    Honours the discriminated-union shape pinned by
    ``contracts/messaging-gateway-payload.md`` §3.2:

    - ``IMAGE`` header → ``{"type": "image", "image_url": <url>}`` —
      requires ``image_url`` (typically pulled from the Lambda's
      ``template_variables.image_url``); returns ``None`` when the URL
      is missing.
    - ``TEXT`` header → ``{"type": "text", "text": <substituted>}``.

    Returns ``None`` when the template has no header.
    """
    header = metadata.get("header")
    if not header:
        return None
    header_type = header.get("header_type")
    if header_type == "IMAGE":
        if not image_url:
            return None
        return {"type": "image", "image_url": image_url}
    if header_type == "TEXT":
        return {
            "type": "text",
            "text": substitute_template_variables(
                header.get("text", ""),
                template_variables,
                template_name=template_name,
            ),
        }
    return None


def build_direct_send_footer(
    metadata: Dict[str, Any],
    template_variables: Dict[str, Any],
    *,
    template_name: str,
) -> Optional[str]:
    """Build the ``msg.footer`` text for the Direct Send payload."""
    footer = metadata.get("footer")
    if not footer:
        return None
    return substitute_template_variables(
        footer, template_variables, template_name=template_name
    )


def build_direct_send_cta_message(
    metadata: Dict[str, Any],
    template_variables: Dict[str, Any],
    *,
    template_name: str,
) -> Optional[Dict[str, Any]]:
    """Build the ``msg.cta_message`` sub-object for the Direct Send payload.

    Reads the single ``URL`` button from ``metadata.buttons`` (FR-003f
    caps URL count at ≤1 at fetch time) and emits the FR-014a wire
    shape ``{display_text, url}`` with both fields substituted
    server-side. Returns ``None`` when no URL button is present so
    the dispatch builder skips ``msg.interaction_type`` and
    ``msg.cta_message``.
    """
    raw_buttons = metadata.get("buttons") or []
    for btn in raw_buttons:
        if btn.get("type") == "URL":
            return {
                "display_text": substitute_template_variables(
                    btn.get("text", ""),
                    template_variables,
                    template_name=template_name,
                ),
                "url": substitute_template_variables(
                    btn.get("url", ""),
                    template_variables,
                    template_name=template_name,
                ),
            }
    return None


def build_direct_send_quick_replies(
    metadata: Dict[str, Any],
    template_variables: Dict[str, Any],
    *,
    template_name: str,
) -> Optional[List[str]]:
    """Build the ``msg.quick_replies`` flat array for the Direct Send payload.

    Reads ``QUICK_REPLY`` entries from ``metadata.buttons`` and emits
    the FR-014b wire shape — a flat list of post-substitution title
    strings (no wrapping object, no ``sub_type`` / ``id`` field; Meta
    library catalog's ``id`` is intentionally not carried on the wire).
    Returns ``None`` when no QUICK_REPLY entry is present so the
    dispatch builder skips ``msg.quick_replies``.
    """
    raw_buttons = metadata.get("buttons") or []
    titles = [
        substitute_template_variables(
            btn.get("text", ""),
            template_variables,
            template_name=template_name,
        )
        for btn in raw_buttons
        if btn.get("type") == "QUICK_REPLY"
    ]
    return titles or None
