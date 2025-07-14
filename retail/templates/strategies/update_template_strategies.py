from abc import ABC, abstractmethod

from typing import Optional, Dict, Any

from uuid import UUID

from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.templates.models import Template
from retail.templates.tasks import task_create_template
from retail.templates.usecases._base_template_creator import TemplateBuilderMixin
from retail.services.rule_generator import RuleGenerator


class UpdateTemplateStrategy(ABC):
    """Abstract strategy for template updates"""

    def __init__(self, template_adapter: Optional[TemplateTranslationAdapter] = None):
        self.template_adapter = template_adapter or TemplateTranslationAdapter()

    @abstractmethod
    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        pass

    def _adapt_translation(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        return self.template_adapter.adapt(metadata)

    def _notify_integrations(
        self,
        version_name: str,
        version_uuid: UUID,
        translation_payload: dict,
        app_uuid: str,
        project_uuid: str,
        category: str,
    ) -> None:
        if not all([version_name, app_uuid, project_uuid, version_uuid]):
            raise ValueError("Missing required data to notify integrations")

        buttons = translation_payload.get("buttons")
        if buttons:
            for button in buttons:
                button["button_type"] = button.pop("type", None)

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
        """
        Atualiza campos comuns de metadata e já retorna o translation_payload
        para evitar chamar _adapt_translation duas vezes.
        """
        if not template.metadata:
            raise ValueError("Template metadata is missing")

        if template.metadata.get("category") is None:
            raise ValueError("Missing category in template metadata")

        updated_metadata = dict(template.metadata)

        updated_metadata["body"] = payload.get(
            "template_body", template.metadata.get("body")
        )
        updated_metadata["body_params"] = payload.get(
            "template_body_params", template.metadata.get("body_params")
        )
        updated_metadata["header"] = payload.get(
            "template_header", template.metadata.get("header")
        )
        updated_metadata["footer"] = payload.get(
            "template_footer", template.metadata.get("footer")
        )
        updated_metadata["buttons"] = payload.get(
            "template_button", template.metadata.get("buttons")
        )

        translation_payload = self._adapt_translation(dict(updated_metadata))
        updated_metadata["buttons"] = translation_payload.get("buttons")
        updated_metadata["header"] = translation_payload.get("header")

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
    ):
        super().__init__(template_adapter)
        self.rule_generator = rule_generator or RuleGenerator()

    def update_template(self, template: Template, payload: Dict[str, Any]) -> Template:
        updated_metadata, translation_payload = self._update_common_metadata(
            template, payload
        )

        if "parameters" in payload:
            generated_code = self.rule_generator.generate_code(
                payload["parameters"], template.integrated_agent
            )
            template.rule_code = generated_code

            start_condition = next(
                (
                    p.get("value")
                    for p in payload["parameters"]
                    if p.get("name") == "start_condition"
                ),
                template.start_condition,
            )

            variables = next(
                (
                    p.get("value")
                    for p in payload["parameters"]
                    if p.get("name") == "variables"
                ),
                template.variables,
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
    ) -> UpdateTemplateStrategy:
        if template.is_custom:
            return UpdateCustomTemplateStrategy(
                template_adapter=template_adapter,
                rule_generator=rule_generator,
            )
        return UpdateNormalTemplateStrategy(template_adapter=template_adapter)
