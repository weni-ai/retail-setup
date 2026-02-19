"""
Utility functions for the templates module.
"""

from typing import Any, Dict, Optional


DEFAULT_TEMPLATE_LANGUAGE = "pt_BR"


def resolve_template_language(
    translation: Optional[Dict[str, Any]] = None,
    agent_config: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Resolve template language using a fallback chain.

    Each dict source is checked for its known language key.
    Callers pass the dicts they already have; this function
    owns the knowledge of which keys to inspect.

    Priority order:
    1. "language" from translation (explicit user choice / existing value)
    2. "initial_template_language" from agent_config
    3. DEFAULT_TEMPLATE_LANGUAGE (pt_BR)

    Note:
        When language info migrates to the Project level,
        add a `project_config` parameter and extract the
        relevant key here.

    Args:
        translation: Payload dict from frontend / template translation.
        agent_config: IntegratedAgent.config dict.

    Returns:
        Resolved language code (e.g., 'pt_BR').
    """
    if translation and translation.get("language"):
        return translation["language"]

    if agent_config and agent_config.get("initial_template_language"):
        return agent_config["initial_template_language"]

    return DEFAULT_TEMPLATE_LANGUAGE
