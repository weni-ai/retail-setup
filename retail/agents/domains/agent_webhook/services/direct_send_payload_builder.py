"""Direct Send payload-building helpers.

Pure functions that translate ``Template.metadata`` + Lambda variables
into the Direct Send wire shape. Anchor: FR-013 / FR-014a / FR-014b /
FR-017 (see ``specs/002-direct-send-broadcasts/spec.md``).
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

    Missing indices substitute to empty string and emit a WARNING so
    operators see rule-engine gaps without halting the broadcast.
    Anchor: FR-013 / Research Decision 6.
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
    """Return True iff ``name`` matches ``^[a-z0-9_]+$`` and ``len <= 512``.

    Anchor: FR-017 / Research Decision 7.
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
    """Build the ``msg.header`` sub-object, or ``None`` when absent.

    Anchor: ``contracts/messaging-gateway-payload.md`` §3.2.
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
    """Build the ``msg.footer`` text, or ``None`` when absent."""
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
    """Build the ``msg.cta_message`` sub-object, or ``None`` when no URL button.

    Anchor: FR-014a (URL count is capped at fetch time by FR-003f).
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
    """Build the flat ``msg.quick_replies`` array, or ``None`` when absent.

    Anchor: FR-014b — Meta library catalog's ``id`` is intentionally
    dropped, only post-substituted titles travel on the wire.
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
