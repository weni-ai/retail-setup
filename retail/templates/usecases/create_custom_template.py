import copy

from typing import Optional, Dict, Any, TypedDict, List

from uuid import UUID

from rest_framework.exceptions import NotFound

from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from retail.templates.usecases import TemplateBuilderMixin
from retail.templates.tasks import task_create_template
from retail.templates.models import Template
from retail.templates.exceptions import CustomTemplateAlreadyExists
from retail.agents.models import IntegratedAgent
from retail.services.rule_generator import RuleGenerator
from retail.templates.handlers import TemplateMetadataHandler


class ParameterData(TypedDict):
    name: str
    value: Any


class CreateCustomTemplateData(TypedDict):
    template_translation: Dict[str, Any]
    category: str
    app_uuid: str
    project_uuid: str
    display_name: str
    start_condition: Optional[str]
    parameters: List[ParameterData]
    integrated_agent_uuid: UUID
    template_name: Optional[str] = None


class CreateCustomTemplateUseCase(TemplateBuilderMixin):
    def __init__(
        self,
        rule_generator: Optional[RuleGenerator] = None,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
        template_metadata_handler: Optional[TemplateMetadataHandler] = None,
    ):
        self.rule_generator = rule_generator or RuleGenerator()
        self.template_adapter = template_adapter or TemplateTranslationAdapter()
        self.metadata_handler = template_metadata_handler or TemplateMetadataHandler()

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
        header = translation_payload.get("header")

        if buttons:
            for button in buttons:
                button["button_type"] = button.pop("type", None)

        if header and header.get("type") == "IMAGE":
            header["example"] = header.pop("text", None)

        task_create_template.delay(
            template_name=version_name,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
            version_uuid=str(version_uuid),
            template_translation=translation_payload,
        )

    def _update_template(
        self,
        template: Template,
        generated_code: str,
        metadata: Dict[str, Any],
        category: str,
        integrated_agent: IntegratedAgent,
        display_name: str,
        start_condition: str,
        variables: Optional[List[Dict[str, Any]]],
    ) -> Template:
        template.integrated_agent = integrated_agent
        template.metadata = metadata
        template.metadata["category"] = category
        template.rule_code = generated_code
        template.display_name = display_name
        template.start_condition = start_condition
        template.variables = variables or []
        template.save()
        return template

    def _get_integrated_agent(self, integrated_agent_uuid: UUID) -> IntegratedAgent:
        try:
            return IntegratedAgent.objects.get(
                uuid=integrated_agent_uuid, is_active=True
            )
        except IntegratedAgent.DoesNotExist:
            raise NotFound(f"Assigned agent not found: {integrated_agent_uuid}")

    def _handle_successful_code_generation(
        self,
        payload: CreateCustomTemplateData,
        generated_code: str,
        integrated_agent: IntegratedAgent,
    ) -> Template:
        if Template.objects.filter(
            integrated_agent=integrated_agent,
            display_name=payload.get("display_name"),
        ).exists():
            raise CustomTemplateAlreadyExists(
                detail="Custom template with this display name already exists"
            )

        payload["template_name"] = payload.get("display_name").replace(" ", "_").lower()

        template, version = self.build_template_and_version(payload, integrated_agent)

        metadata = self.metadata_handler.build_metadata(
            payload.get("template_translation", {}),
            payload.get("category"),
        )

        translation_payload = self.template_adapter.adapt(metadata)

        metadata = self.metadata_handler.post_process_translation(
            metadata, translation_payload
        )

        start_condition = self.metadata_handler.extract_start_condition(
            payload.get("parameters", []),
            None,
        )

        variables = self.metadata_handler.extract_variables(
            payload.get("parameters", []),
            None,
        )

        template = self._update_template(
            template,
            generated_code,
            metadata,
            payload.get("category"),
            integrated_agent,
            payload.get("display_name"),
            start_condition,
            variables,
        )
        self._notify_integrations(
            version.template_name,
            version.uuid,
            copy.deepcopy(translation_payload),
            payload.get("app_uuid"),
            payload.get("project_uuid"),
            payload.get("category"),
        )
        return template

    def execute(self, payload: CreateCustomTemplateData) -> Template:
        """
        Executes the custom template creation flow.

        Args:
            payload (CreateCustomTemplateData): The input data containing template content and rule code.

        Returns:
            Template: The created template instance.
        """
        integrated_agent = self._get_integrated_agent(
            payload.get("integrated_agent_uuid")
        )

        generated_code = self.rule_generator.generate_code(
            payload["parameters"], integrated_agent
        )

        return self._handle_successful_code_generation(
            payload, generated_code, integrated_agent
        )
