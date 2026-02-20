"""
Utility functions for the templates module.
"""

import logging
import re

from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger(__name__)

DEFAULT_TEMPLATE_LANGUAGE = "pt_BR"


class TemplateVariableMapper:
    """
    Handles conversion between labeled variables ({{client_name}})
    and numeric variables ({{1}}) for Meta WhatsApp templates.

    The template body is the source of truth for variable ordering.
    Variables are numbered based on their order of appearance in the text.

    Example:
        body = "Hello {{client_name}}, your order {{order_id}} arrives {{delivery_date}}"
        mapping = {"client_name": 1, "order_id": 2, "delivery_date": 3}
    """

    # Pattern to match {{variable_name}} - captures alphanumeric and underscore
    LABELED_VARIABLE_PATTERN = re.compile(r"\{\{(\w+)\}\}")
    # Pattern to match {{1}}, {{2}}, etc - numeric only
    NUMERIC_VARIABLE_PATTERN = re.compile(r"\{\{(\d+)\}\}")

    @classmethod
    def extract_variable_labels(cls, template_body: str) -> List[str]:
        """
        Extract variable labels from template body in order of appearance.

        Args:
            template_body: Template text with {{variable_name}} placeholders.

        Returns:
            List of variable names in order of appearance (excluding numeric ones).

        Example:
            >>> TemplateVariableMapper.extract_variable_labels(
            ...     "Hello {{client_name}}, order {{order_id}}"
            ... )
            ['client_name', 'order_id']
        """
        if not template_body:
            return []

        matches = cls.LABELED_VARIABLE_PATTERN.findall(template_body)
        # Filter out numeric-only matches (already converted templates)
        return [m for m in matches if not m.isdigit()]

    @classmethod
    def build_variable_mapping(cls, template_body: str) -> Dict[str, int]:
        """
        Build mapping from variable labels to their numeric positions.

        The position is determined by the order of appearance in the template body.
        This mapping is the "source of truth" for variable ordering.

        Args:
            template_body: Template text with {{variable_name}} placeholders.

        Returns:
            Dict mapping label to position (1-indexed).

        Example:
            >>> TemplateVariableMapper.build_variable_mapping(
            ...     "Hello {{client_name}}, order {{order_id}}"
            ... )
            {'client_name': 1, 'order_id': 2}
        """
        labels = cls.extract_variable_labels(template_body)
        return {label: idx + 1 for idx, label in enumerate(labels)}

    @classmethod
    def convert_body_to_numeric(cls, template_body: str) -> str:
        """
        Convert labeled variables to numeric format for Meta API.

        Args:
            template_body: Template with {{variable_name}} placeholders.

        Returns:
            Template with {{1}}, {{2}}, etc.

        Example:
            >>> TemplateVariableMapper.convert_body_to_numeric(
            ...     "Hello {{client_name}}, order {{order_id}}"
            ... )
            'Hello {{1}}, order {{2}}'
        """
        if not template_body:
            return template_body

        counter = [0]

        def replace_match(match):
            var_name = match.group(1)
            # Skip if already numeric
            if var_name.isdigit():
                return match.group(0)
            counter[0] += 1
            return f"{{{{{counter[0]}}}}}"

        return cls.LABELED_VARIABLE_PATTERN.sub(replace_match, template_body)

    @classmethod
    def map_labeled_variables_to_numeric(
        cls,
        variables: Dict[str, Any],
        mapping: Dict[str, int],
    ) -> Tuple[Dict[str, Any], List[str]]:
        """
        Convert labeled variables dict to numeric keys for broadcast.

        Special keys (button, image_url) are preserved as-is.

        Args:
            variables: Dict with label keys {"client_name": "João", "order_id": "123"}
            mapping: Label to position mapping {"client_name": 1, "order_id": 2}

        Returns:
            Tuple containing:
            - Dict with numeric keys {"1": "João", "2": "123"}
            - List of unknown variable labels (not found in mapping)

        Example:
            >>> variables = {"client_name": "João", "order_id": "123"}
            >>> mapping = {"client_name": 1, "order_id": 2}
            >>> TemplateVariableMapper.map_labeled_variables_to_numeric(variables, mapping)
            ({"1": "João", "2": "123"}, [])
        """
        SPECIAL_KEYS = {"button", "image_url"}

        result = {}
        unknown_labels = []

        for label, value in variables.items():
            if label in SPECIAL_KEYS:
                result[label] = value
            elif label in mapping:
                result[str(mapping[label])] = value
            else:
                # Check if it's already a numeric key
                if label.isdigit():
                    result[label] = value
                else:
                    unknown_labels.append(label)

        return result, unknown_labels

    @classmethod
    def has_labeled_variables(cls, variables: Dict[str, Any]) -> bool:
        """
        Check if variables dict contains labeled (non-numeric) keys.

        Args:
            variables: Dict of template variables.

        Returns:
            True if any key is a non-numeric, non-special label.

        Example:
            >>> TemplateVariableMapper.has_labeled_variables({"client_name": "João"})
            True
            >>> TemplateVariableMapper.has_labeled_variables({"1": "João", "button": "x"})
            False
        """
        SPECIAL_KEYS = {"button", "image_url"}

        for key in variables:
            if key not in SPECIAL_KEYS and not key.isdigit():
                return True
        return False


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
