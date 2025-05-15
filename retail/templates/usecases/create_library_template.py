from typing import Optional, TypedDict, List, Dict, Any

from uuid import UUID

from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.services.integrations.service import IntegrationsService
from retail.templates.models import Template
from retail.templates.tasks import task_create_library_template

from ._base_template_creator import TemplateBuilderMixin


class CreateLibraryTemplateData(TypedDict):
    template_name: str
    library_template_name: str
    category: str
    language: str
    app_uuid: str
    project_uuid: str
    start_condition: str
    library_template_button_inputs: Optional[List[Dict[str, Any]]] = None


class CreateLibraryTemplateUseCase(TemplateBuilderMixin):
    def __init__(self, service: Optional[IntegrationsServiceInterface] = None):
        self.service = service or IntegrationsService()

    def _notify_integrations(
        self, version_name: str, version_uuid: UUID, payload: CreateLibraryTemplateData
    ) -> None:
        if (
            not version_name
            or not payload.get("app_uuid")
            or not payload.get("project_uuid")
            or not version_uuid
        ):
            raise ValueError("Missing required data to notify integrations")

        task_create_library_template.delay(
            name=version_name,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=payload["category"],
            language=payload["language"],
            library_template_name=payload["library_template_name"],
            gallery_version=str(version_uuid),
            library_template_button_inputs=payload.get(
                "library_template_button_inputs"
            ),
        )

    def execute(self, payload: CreateLibraryTemplateData) -> Template:
        template, version = self.build_template_and_version(payload)
        self._notify_integrations(version.template_name, version.uuid, payload)
        return template
