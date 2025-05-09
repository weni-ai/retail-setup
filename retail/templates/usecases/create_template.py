from retail.interfaces.services.integrations import IntegrationsServiceInterface
from retail.templates.services.integrations import IntegrationsService
from retail.templates.models import Template, Version
from retail.projects.models import Project
from retail.templates.exceptions import IntegrationsServerError

from rest_framework.exceptions import NotFound

from typing import Optional, TypedDict, Dict, Any

from uuid import UUID

from datetime import datetime


class CreateTemplateData(TypedDict):
    template_translation: Dict[str, Any]
    template_name: str
    start_condition: str
    category: str
    app_uuid: str
    project_uuid: str


class CreateTemplateUseCase:
    def __init__(self, service: Optional[IntegrationsServiceInterface] = None):
        self.service = service or IntegrationsService()

    def _create_template(self, name: str, start_condition: str) -> Template:
        template = Template(
            name=name,
            start_condition=start_condition,
            current_version=None,
        )
        template.full_clean()
        template.save()
        return template

    def _create_version(
        self, template: Template, app_uuid: str, project_uuid: str
    ) -> Version:
        project = self._get_project(project_uuid)
        template_name = template.name
        timestamp_str = str(datetime.now().timestamp()).replace(".", "")
        version_name = f"weni_{template_name}_{timestamp_str}"
        version = Version(
            template_name=version_name,
            template=template,
            integrations_app_uuid=app_uuid,
            project=project,
        )
        version.full_clean()
        version.save()
        return version

    def _notify_integrations(
        self, version_name: str, version_uuid: UUID, payload: CreateTemplateData
    ) -> None:
        try:
            template_uuid = self.service.create_template(
                app_uuid=payload.get("app_uuid"),
                project_uuid=payload.get("project_uuid"),
                name=version_name,
                category=payload.get("category"),
                gallery_version=str(version_uuid),
            )
            self.service.create_template_translation(
                app_uuid=payload.get("app_uuid"),
                project_uuid=payload.get("project_uuid"),
                template_uuid=template_uuid,
                payload=payload.get("template_translation"),
            )
        except Exception:
            raise IntegrationsServerError()

    def _get_project(self, project_uuid: str) -> Project:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise NotFound(f"Project not found: {project_uuid}")

    def execute(self, payload: CreateTemplateData) -> Template:

        template = Template.objects.filter(name=payload.get("template_name")).first()

        if not template:
            template = self._create_template(
                name=payload.get("template_name"),
                start_condition=payload.get("start_condition"),
            )

        version = self._create_version(
            template=template,
            app_uuid=payload.get("app_uuid"),
            project_uuid=payload.get("project_uuid"),
        )

        self._notify_integrations(version.template_name, version.uuid, payload)

        return template
