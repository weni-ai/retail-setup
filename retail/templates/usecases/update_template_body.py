from uuid import UUID
from typing import Optional, TypedDict

from rest_framework.exceptions import NotFound

from retail.templates.models import Template
from retail.templates.tasks import task_create_template
from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.services.integrations.service import IntegrationsService
from retail.templates.adapters.template_library_to_custom_adapter import (
    adapt_library_template_to_translation,
)
from ._base_template_creator import TemplateBuilderMixin


class UpdateTemplateContentData(TypedDict):
    template_uuid: str
    template_body: str
    template_header: str
    template_footer: str
    app_uuid: str
    project_uuid: str


class UpdateTemplateContentUseCase(TemplateBuilderMixin):
    """
    Updates the body of a template using its metadata and triggers a new version with integrations.
    """

    def __init__(self, service: Optional[IntegrationsServiceInterface] = None):
        self.service = service or IntegrationsService()

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

        task_create_template(
            template_name=version_name,
            app_uuid=app_uuid,
            project_uuid=project_uuid,
            category=category,
            version_uuid=str(version_uuid),
            template_translation=translation_payload,
        )

    def execute(self, payload: UpdateTemplateContentData) -> Template:
        """
        Updates template content fields (body, header, footer) based on metadata and creates a new version.

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

        updated_fields = False

        if payload.get("template_body"):
            updated_metadata["body"] = payload["template_body"]
            updated_fields = True
        if payload.get("template_header"):
            updated_metadata["header"] = payload["template_header"]
            updated_fields = True
        if payload.get("template_footer"):
            updated_metadata["footer"] = payload["template_footer"]
            updated_fields = True

        if updated_fields:
            # Persist changes into the Template.metadata
            template.metadata = updated_metadata
            template.save(update_fields=["metadata"])

        translation_payload = adapt_library_template_to_translation(updated_metadata)

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
