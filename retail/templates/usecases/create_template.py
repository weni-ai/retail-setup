from typing import Optional, TypedDict, Dict, Any

from uuid import UUID

from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.services.integrations.service import IntegrationsService
from retail.templates.models import Template
from retail.templates.tasks import task_create_template

from ._base_template_creator import TemplateBuilderMixin


class CreateTemplateData(TypedDict):
    template_translation: Dict[str, Any]
    template_name: str
    start_condition: str
    category: str
    app_uuid: str
    project_uuid: str


class CreateTemplateUseCase(TemplateBuilderMixin):
    def __init__(self, service: Optional[IntegrationsServiceInterface] = None):
        self.service = service or IntegrationsService()

    def _notify_integrations(
        self, version_name: str, version_uuid: UUID, payload: CreateTemplateData
    ) -> None:
        if not all(
            [
                version_name,
                payload.get("app_uuid"),
                payload.get("project_uuid"),
                version_uuid,
            ]
        ):
            raise ValueError("Missing required data to notify integrations")

        task_create_template.delay(
            template_name=version_name,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
            category=payload["category"],
            version_uuid=str(version_uuid),
            template_translation=payload["template_translation"],
        )

    def execute(self, payload: CreateTemplateData) -> Template:
        template, version = self.build_template_and_version(payload)
        self._notify_integrations(version.template_name, version.uuid, payload)
        return template
