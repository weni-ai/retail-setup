"""Align a Lambda payload with the components the approved template still declares.

Agents keep returning the original variables and buttons after an operator
removes them from the template. Flows rejects that payload, so the dispatch
path drops anything the stored template no longer contains. When the template
does not record a component (legacy metadata), the Lambda payload is kept.
"""

import logging
import re
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)

_POSITIONAL_VARIABLE = re.compile(r"\{\{\s*(\d+)\s*\}\}")


def declared_body_variable_indexes(body: Any) -> Optional[Set[int]]:
    """Indexes present in the body, or None when the body was not stored."""
    if not isinstance(body, str):
        return None
    return {int(match) for match in _POSITIONAL_VARIABLE.findall(body)}


def should_include_url_button(buttons: Any) -> bool:
    """Send the Lambda URL suffix only when the template URL still has a placeholder.

    Missing ``buttons`` keeps the legacy behavior (include the suffix). An
    explicit list that has no dynamic URL button means the operator removed it.
    """
    if not isinstance(buttons, list):
        return True

    return any(
        isinstance(button, dict)
        and button.get("type") == "URL"
        and _POSITIONAL_VARIABLE.search(str(button.get("url") or ""))
        for button in buttons
    )


def align_payment_buttons(
    lambda_buttons: Optional[List[Dict[str, Any]]],
    template_buttons: Any,
) -> List[Dict[str, Any]]:
    """Keep Lambda payment buttons that the template still declares, in template order.

    Untyped ``PAYMENT_REQUEST`` entries cannot be matched, so the Lambda list
    is preserved. Typed entries are the contract written at template creation.
    """
    if not lambda_buttons:
        return []
    if not isinstance(template_buttons, list):
        return list(lambda_buttons)

    declared_types = _declared_payment_types(template_buttons)
    if declared_types is None:
        return list(lambda_buttons)

    by_type = {
        button.get("type"): button
        for button in lambda_buttons
        if isinstance(button, dict) and button.get("type")
    }
    selected = [
        by_type[payment_type]
        for payment_type in declared_types
        if payment_type in by_type
    ]
    dropped = [
        payment_type for payment_type in by_type if payment_type not in declared_types
    ]
    if dropped:
        logger.info(
            f"Omitted payment buttons absent from the template: types={dropped}"
        )
    return selected


def _declared_payment_types(template_buttons: List[Any]) -> Optional[List[str]]:
    declared_types: List[str] = []
    saw_untyped_payment_button = False

    for button in template_buttons:
        if not isinstance(button, dict) or button.get("type") != "PAYMENT_REQUEST":
            continue
        payment_type = (button.get("payment_setting") or {}).get("type")
        if payment_type:
            declared_types.append(payment_type)
        else:
            saw_untyped_payment_button = True

    if saw_untyped_payment_button and not declared_types:
        return None
    return declared_types
