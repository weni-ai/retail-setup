from uuid import UUID
from typing import Optional, TypedDict, List, Dict, Any

from rest_framework.exceptions import NotFound

from retail.templates.models import Template
from retail.templates.tasks import task_create_template
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.services.integrations.service import IntegrationsService
from retail.templates.adapters.template_library_to_custom_adapter import (
    TemplateTranslationAdapter,
)
from ._base_template_creator import TemplateBuilderMixin


class UpdateTemplateContentData(TypedDict):
    template_uuid: str
    template_body: str
    template_header: str
    template_footer: str
    template_button: List[Dict[str, Any]]
    app_uuid: str
    project_uuid: str


class UpdateTemplateContentUseCase(TemplateBuilderMixin):
    """
    Updates the body of a template using its metadata and triggers a new version with integrations.

    Example of using custom transformers for specific business logic:

    # Custom transformer example
    class CustomBodyTransformer(ComponentTransformer):
        def transform(self, template_data: Dict) -> Dict:
            # Custom business logic for body transformation
            body_data = {"type": "BODY", "text": template_data["body"]}
            # Add custom validation or formatting here
            return body_data

    # Usage with custom transformers
    custom_adapter = TemplateTranslationAdapter(
        body_transformer=CustomBodyTransformer()
    )
    use_case = UpdateTemplateContentUseCase(template_adapter=custom_adapter)
    """

    def __init__(
        self,
        service: Optional[IntegrationsServiceInterface] = None,
        template_adapter: Optional[TemplateTranslationAdapter] = None,
    ):
        self.service = service or IntegrationsService()
        self.template_adapter = template_adapter or TemplateTranslationAdapter()

    def _get_template(self, uuid: str) -> Template:
        try:
            return Template.objects.get(uuid=uuid)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {uuid}")

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

        task_create_template.delay(
            template_name=version_name,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
            version_uuid=str(version_uuid),
            template_translation=translation_payload,
        )

    def execute(self, payload: UpdateTemplateContentData) -> Template:
        """
        Updates template content fields (body, header, footer, buttons) based on metadata and creates a new version.

        Args:
            payload (UpdateTemplateContentData): The update input including optional content fields
            and required context.

        Returns:
            Template: The template instance with a new version propagated to integrations.
        """
        template = self._get_template(payload["template_uuid"])

        if not template.metadata:
            raise ValueError("Template metadata is missing")

        category = template.metadata.get("category")

        if not category:
            raise ValueError("Missing category in template metadata")

        updated_metadata = dict(template.metadata)

        updated_metadata["body"] = payload.get(
            "template_body", template.metadata.get("body")
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

        translation_payload = self.template_adapter.adapt(updated_metadata)

        updated_metadata["buttons"] = translation_payload.get("buttons")

        template.metadata = updated_metadata
        template.save(update_fields=["metadata"])

        buttons = updated_metadata.get("buttons")

        if buttons:
            for button in buttons:
                button["button_type"] = button.pop("type", None)

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

        return template
