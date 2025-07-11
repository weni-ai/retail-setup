from typing import Optional, TypedDict, List, Dict, Any

from rest_framework.exceptions import NotFound

from retail.templates.models import Template
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.services.rule_generator import RuleGenerator


class UpdateTemplateContentData(TypedDict):
    template_uuid: str
    template_body: str
    template_header: str
    template_footer: str
    template_button: List[Dict[str, Any]]
    app_uuid: str
    project_uuid: str
    parameters: Optional[List[Dict[str, Any]]]


class UpdateTemplateContentUseCase:
    """
    Updates the content of a template using Strategy Pattern for different template types.

    This use case handles both normal and custom templates:
    - Normal templates: Updates body, header, footer, buttons directly
    - Custom templates: Updates content and generates new code using parameters

    Example usage:

    # For normal templates
    payload = {
        "template_uuid": "some-uuid",
        "template_body": "Updated body",
        "app_uuid": "app-uuid",
        "project_uuid": "project-uuid",
        # ... other fields
    }

    # For custom templates
    payload = {
        "template_uuid": "some-uuid",
        "template_body": "Updated body",
        "parameters": [{"name": "param1", "value": "value1"}],
        "app_uuid": "app-uuid",
        "project_uuid": "project-uuid",
        # ... other fields
    }

    use_case = UpdateTemplateContentUseCase()
    updated_template = use_case.execute(payload)
    """

    def __init__(
        self,
        rule_generator: Optional[RuleGenerator] = None,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
    ):
        self.rule_generator = rule_generator
        self.template_adapter = template_adapter

    def _get_template(self, uuid: str) -> Template:
        """Retrieve template by UUID"""
        try:
            return Template.objects.get(uuid=uuid)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {uuid}")

    def execute(self, payload: UpdateTemplateContentData) -> Template:
        """
        Updates template content using the appropriate strategy based on template type.

        Args:
            payload (UpdateTemplateContentData): The update input including content fields,
            context data, and optional parameters for custom templates.

        Returns:
            Template: The updated template instance with a new version propagated to integrations.
        """
        from retail.templates.strategies.update_template_strategies import (
            UpdateTemplateStrategyFactory,
        )

        template = self._get_template(payload["template_uuid"])

        strategy = UpdateTemplateStrategyFactory.create_strategy(
            template=template,
            template_adapter=self.template_adapter,
            rule_generator=self.rule_generator,
        )

        return strategy.update_template(template, payload)
