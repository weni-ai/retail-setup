"""
Utility classes and functions for agent integration domain.
"""

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class TemplateLanguage:
    """Represents a template language with its Meta code and display name."""

    code: str
    display_name: str


# Available template languages for abandoned cart agent
TEMPLATE_LANGUAGES: List[TemplateLanguage] = [
    TemplateLanguage(code="pt_BR", display_name="Português (BR)"),
    TemplateLanguage(code="en", display_name="English (US)"),
    TemplateLanguage(code="es", display_name="Español"),
]

# Default language when none is specified
DEFAULT_TEMPLATE_LANGUAGE_CODE = "pt_BR"
