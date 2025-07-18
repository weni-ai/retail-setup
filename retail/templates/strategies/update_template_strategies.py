# retail/templates/strategies/update_template_strategies.py

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
from uuid import UUID

from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.templates.models import Template
from retail.templates.usecases import TemplateBuilderMixin
from retail.services.rule_generator import RuleGenerator
from retail.templates.handlers import TemplateMetadataHandler
from retail.templates.tasks import task_create_template


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
            header["example"] = header.pop("text", None)

        task_create_template.delay(
            template_name=version_name,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
            version_uuid=str(version_uuid),
            template_translation=translation_payload,
        )

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
