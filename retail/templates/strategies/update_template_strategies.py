# retail/templates/strategies/update_template_strategies.py

import logging
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from uuid import UUID

from django.conf import settings

from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.templates.models import Template
from retail.templates.usecases import TemplateBuilderMixin
from retail.services.rule_generator import RuleGenerator
from retail.templates.handlers import TemplateMetadataHandler
from retail.templates.tasks import task_create_template
from retail.agents.shared.cache import IntegratedAgentCacheHandlerRedis
from retail.services.aws_s3.converters import ImageUrlToBase64Converter

logger = logging.getLogger(__name__)


class UpdateTemplateStrategy(ABC):
    """Abstract strategy for template updates"""

    def __init__(
        self,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
        template_metadata_handler: Optional[TemplateMetadataHandler] = None,
    ):
        self.template_adapter = template_adapter or TemplateTranslationAdapter()
        self.metadata_handler = template_metadata_handler or TemplateMetadataHandler()

    @abstractmethod
    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        pass

    def _notify_integrations(
        self,
        version_name: str,
        version_uuid: UUID,
        translation_payload: dict,
        app_uuid: str,
        project_uuid: str,
        category: str,
    ) -> None:
        buttons = translation_payload.get("buttons")
        if buttons:
            for button in buttons:
                button["button_type"] = button.pop("type", None)

        header = translation_payload.get("header")

        if isinstance(header, dict) and header.get("header_type") == "IMAGE":
            header_content = header.pop("text", None)
            header["example"] = self._convert_image_url_to_base64_if_needed(
                header_content
            )

        task_create_template.delay(
            template_name=version_name,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
            version_uuid=str(version_uuid),
            template_translation=translation_payload,
        )

    def _convert_image_url_to_base64_if_needed(self, image_content: str) -> str:
        """
        Convert image URL to base64 Data URI if content is a URL.
        Returns the original content if it's already base64 or conversion fails.
        """
        if not image_content:
            return image_content

        # Already in base64 Data URI format
        if image_content.startswith("data:"):
            return image_content

        # Try to convert URL to base64
        converter = ImageUrlToBase64Converter()
        if converter.is_image_url(image_content):
            converted = converter.convert(image_content)
            if converted:
                logger.info("Successfully converted image URL to base64 for template")
                return converted
            else:
                logger.warning(
                    "Failed to convert image URL to base64, using original content"
                )

        return image_content

    def _update_common_metadata(
        self, template: Template, payload: Dict[str, Any]
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        updated_metadata = self.metadata_handler.build_metadata(
            payload,
            template.metadata.get("category"),
        )
        translation_payload = self.template_adapter.adapt(updated_metadata)

        updated_metadata = self.metadata_handler.post_process_translation(
            updated_metadata, translation_payload
        )
        return updated_metadata, translation_payload

    def _create_version_and_notify(
        self,
        template: Template,
        payload: Dict[str, Any],
        translation_payload: Dict[str, Any],
    ) -> None:
        category = template.metadata.get("category")

        version = self._create_version(
            template=template,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
        )

        self._notify_integrations(
            version_name=version.template_name,
            version_uuid=version.uuid,
            translation_payload=translation_payload,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=category,
        )

    def _sync_abandoned_cart_image_config(
        self, template: Template, translation_payload: Dict[str, Any]
    ) -> None:
        """
        Sync the abandoned cart agent's header_image_type config based on template header.

        If the template belongs to an abandoned cart agent and the header image is removed,
        automatically update the agent's config to 'no_image' to prevent runtime errors.

        Args:
            template: The template being updated.
            translation_payload: The translation payload with header info.
        """
        # Check if template has an integrated agent
        if not template.integrated_agent:
            return

        integrated_agent = template.integrated_agent

        # Check if this is an abandoned cart agent
        abandoned_cart_agent_uuid = getattr(settings, "ABANDONED_CART_AGENT_UUID", "")
        if not abandoned_cart_agent_uuid:
            return

        if str(integrated_agent.agent.uuid) != abandoned_cart_agent_uuid:
            return

        # Check if header has image or not
        header = translation_payload.get("header", {})
        has_image_header = (
            isinstance(header, dict) and header.get("header_type") == "IMAGE"
        )

        # Get current config
        config = integrated_agent.config or {}
        abandoned_cart_config = config.get("abandoned_cart", {})
        current_image_type = abandoned_cart_config.get(
            "header_image_type", "first_item"
        )

        # Determine new image type based on template header
        new_image_type = None

        if not has_image_header and current_image_type != "no_image":
            # Template has no image but config expects image -> update to no_image
            new_image_type = "no_image"
        elif has_image_header and current_image_type == "no_image":
            # Template has image but config is no_image -> update to first_item (default)
            new_image_type = "first_item"

        # Update config if needed
        if new_image_type:
            abandoned_cart_config["header_image_type"] = new_image_type
            config["abandoned_cart"] = abandoned_cart_config
            integrated_agent.config = config
            integrated_agent.save(update_fields=["config"])

            # Clear webhook cache (30 seconds) so new config is used immediately
            self._clear_agent_cache(integrated_agent.uuid)

            logger.info(
                f"Synced abandoned cart config for agent {integrated_agent.uuid}: "
                f"header_image_type changed from '{current_image_type}' to '{new_image_type}'"
            )

    def _clear_agent_cache(self, integrated_agent_uuid) -> None:
        """Clear the webhook cache for the integrated agent."""
        cache_handler = IntegratedAgentCacheHandlerRedis()
        cache_handler.clear_cached_agent(integrated_agent_uuid)


class UpdateNormalTemplateStrategy(UpdateTemplateStrategy, TemplateBuilderMixin):
    """Strategy for updating normal templates"""

    def __init__(
        self,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
        template_metadata_handler: Optional[TemplateMetadataHandler] = None,
    ):
        super().__init__(template_adapter, template_metadata_handler)

    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        updated_metadata, translation_payload = self._update_common_metadata(
            template, payload
        )

        template.metadata = updated_metadata
        template.save(update_fields=["metadata"])

        # Sync abandoned cart agent config if header image was added/removed
        self._sync_abandoned_cart_image_config(template, translation_payload)

        self._create_version_and_notify(template, payload, translation_payload)

        return template


class UpdateCustomTemplateStrategy(UpdateTemplateStrategy, TemplateBuilderMixin):
    """Strategy for updating custom templates"""

    def __init__(
        self,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
        rule_generator: Optional[RuleGenerator] = None,
        template_metadata_handler: Optional[TemplateMetadataHandler] = None,
    ):
        super().__init__(template_adapter, template_metadata_handler)
        self.rule_generator = rule_generator or RuleGenerator()

    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        updated_metadata, translation_payload = self._update_common_metadata(
            template, payload
        )

        parameters = payload.get("parameters", [])

        if parameters:
            generated_code = self.rule_generator.generate_code(
                parameters, template.integrated_agent
            )
            template.rule_code = generated_code

            start_condition = self.metadata_handler.extract_start_condition(
                parameters,
                None,
            )

            variables = self.metadata_handler.extract_variables(
                parameters,
                None,
            )

            template.start_condition = start_condition
            template.variables = variables or []

        template.metadata = updated_metadata
        template.save()

        # Sync abandoned cart agent config if header image was added/removed
        self._sync_abandoned_cart_image_config(template, translation_payload)

        self._create_version_and_notify(template, payload, translation_payload)

        return template


class UpdateTemplateStrategyFactory:
    """Factory for creating appropriate update template strategies"""

    @staticmethod
    def create_strategy(
        template: Template,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
        rule_generator: Optional[RuleGenerator] = None,
        template_metadata_handler: Optional[TemplateMetadataHandler] = None,
    ) -> "UpdateTemplateStrategy":
        if template.is_custom:
            return UpdateCustomTemplateStrategy(
                template_adapter=template_adapter,
                rule_generator=rule_generator,
                template_metadata_handler=template_metadata_handler,
            )
        return UpdateNormalTemplateStrategy(
            template_adapter=template_adapter,
            template_metadata_handler=template_metadata_handler,
        )
