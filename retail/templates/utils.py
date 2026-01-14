"""
Utility functions for the templates module.
"""

from typing import Any, Dict, Optional

from retail.templates.models import Template


DEFAULT_TEMPLATE_LANGUAGE = "pt_BR"


def resolve_template_language(
    template: Template, payload: Optional[Dict[str, Any]] = None
) -> str:
    """
    Resolve template language with fallback chain.

    Priority order:
    1. Explicit language from payload (user choice from frontend)
    2. initial_template_language from integrated_agent config (project default)
    3. language from template metadata (current template language)
    4. Default to pt_BR

    Args:
        template: The template being updated.
        payload: Optional payload dict that may contain 'language' key.

    Returns:
        Resolved language code (e.g., 'pt_BR', 'en', 'es').
    """
    # 1. Explicit language from payload
    if payload and payload.get("language"):
        return payload["language"]

    # 2. Try to get from integrated agent config
    if template.integrated_agent:
        agent_language = template.integrated_agent.config.get(
            "initial_template_language"
        )
        if agent_language:
            return agent_language

    # 3. Fallback to template metadata
    if template.metadata and template.metadata.get("language"):
        return template.metadata.get("language")

    # 4. Default
    return DEFAULT_TEMPLATE_LANGUAGE
