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

The header / footer / buttons builders consume the ``Template.metadata``
shape produced by ``_get_template_info`` /
``adapt_meta_library_template_response`` (data-model.md §3).
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


def build_direct_send_buttons(
    metadata: Dict[str, Any],
    template_variables: Dict[str, Any],
    *,
    template_name: str,
) -> Optional[List[Dict[str, Any]]]:
    """Build the ``msg.buttons`` list for the Direct Send payload.

    Maps Meta library-catalog button types to Direct Send sub_types
    (research Decision 8; ``contracts/messaging-gateway-payload.md``
    §3.3):

    - ``URL`` → ``{"sub_type": "cta_url", "display_text", "url"}``
      with the URL substituted server-side.
    - ``QUICK_REPLY`` → ``{"sub_type": "reply", "id", "title"}`` with
      the title substituted; ``id`` defaults to the literal title
      when the source button carries no explicit id (Meta's library
      catalog response does not surface one).
    """
    raw_buttons = metadata.get("buttons")
    if not raw_buttons:
        return None

    result: List[Dict[str, Any]] = []
    for btn in raw_buttons:
        btn_type = btn.get("type")
        if btn_type == "URL":
            result.append(
                {
                    "sub_type": "cta_url",
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
            )
        elif btn_type == "QUICK_REPLY":
            title = substitute_template_variables(
                btn.get("text", ""),
                template_variables,
                template_name=template_name,
            )
            result.append(
                {
                    "sub_type": "reply",
                    "id": btn.get("id") or title,
                    "title": title,
                }
            )
    return result or None
