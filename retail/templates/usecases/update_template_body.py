import copy
import logging
from typing import Any, Dict, List, Optional, TypedDict

from django.conf import settings
from rest_framework.exceptions import NotFound

from retail.services.aws_s3.converters import ImageUrlToBase64Converter
from retail.services.rule_generator import RuleGenerator
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.templates.exceptions import DefaultHeaderImageUnavailable
from retail.templates.models import Template

logger = logging.getLogger(__name__)


class UpdateTemplateContentData(TypedDict, total=False):
    template_uuid: str
    template_body: str
    template_header: str
    template_footer: str
    template_button: list
    template_body_params: list
    app_uuid: str
    project_uuid: str
    parameters: Optional[List[Dict[str, Any]]]
    language: Optional[str]
    use_default_header_image: bool


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
        image_converter: Optional[ImageUrlToBase64Converter] = None,
    ):
        self.rule_generator = rule_generator
        self.template_adapter = template_adapter
        self.image_converter = image_converter or ImageUrlToBase64Converter()

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
        resolved_payload = self._resolve_default_header_image(dict(payload))
        resolved_payload = self._preserve_buttons_when_omitted(
            template, resolved_payload
        )

        strategy = UpdateTemplateStrategyFactory.create_strategy(
            template=template,
            template_adapter=self.template_adapter,
            rule_generator=self.rule_generator,
        )

        return strategy.update_template(template, resolved_payload)

    def _resolve_default_header_image(
        self, payload: UpdateTemplateContentData
    ) -> UpdateTemplateContentData:
        """Replace the flag with the agent default image.

        The update strategy only understands ``template_header``. ``True``
        reuses the image agent creation already converts for Integrations.
        ``False`` omits the header so the stored image is removed.
        """
        use_default_header_image = payload.pop("use_default_header_image", None)
        if use_default_header_image is None:
            return payload

        if not use_default_header_image:
            payload.pop("template_header", None)
            return payload

        image_url = settings.ABANDONED_CART_DEFAULT_IMAGE_URL
        header_image = self.image_converter.convert(image_url)
        if not header_image:
            logger.error(f"Default header image could not be loaded from {image_url}")
            raise DefaultHeaderImageUnavailable()

        payload["template_header"] = header_image
        logger.info("Resolved the default header image for the template update")
        return payload

    def _preserve_buttons_when_omitted(
        self, template: Template, payload: UpdateTemplateContentData
    ) -> UpdateTemplateContentData:
        """Keep stored buttons when the edit does not mention them.

        A missing ``template_button`` used to become ``buttons: null``, which
        drops the buttons on Meta and is treated as a legacy template on
        dispatch. The copy is required because the Integrations payload
        mutates each button in place.
        """
        if "template_button" in payload:
            return payload

        stored_buttons = (template.metadata or {}).get("buttons")
        payload["template_button"] = copy.deepcopy(stored_buttons)
        logger.info(
            "template_button omitted; keeping the buttons stored on the template"
        )
        return payload
