from datetime import datetime
from typing import Optional, Tuple

from rest_framework.exceptions import NotFound

from retail.agents.models import IntegratedAgent
from retail.templates.models import Template, Version
from retail.projects.models import Project


from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .create_template import CreateTemplateData
    from .create_library_template import CreateLibraryTemplateData


class TemplateBuilderMixin:
    def _create_template(
        self,
        name: str,
        start_condition: Optional[str] = None,
    ) -> Template:
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
        timestamp_str = str(datetime.now().timestamp()).replace(".", "")
        version_name = f"weni_{template.name}_{timestamp_str}"
        version = Version(
            template_name=version_name,
            template=template,
            integrations_app_uuid=app_uuid,
            project=project,
        )
        version.full_clean()
        version.save()
        return version

    def _get_project(self, project_uuid: str) -> Project:
        try:
            return Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist:
            raise NotFound(f"Project not found: {project_uuid}")

    def build_template_and_version(
        self,
        payload: "CreateTemplateData | CreateLibraryTemplateData",
        integrated_agent: Optional[IntegratedAgent] = None,
    ) -> Tuple[Template, Version]:
        """
        Centralized logic to create or retrieve a template and create a new version.

        Args:
            payload: Dict-like object containing template_name, start_condition, app_uuid, project_uuid.

        Returns:
            Tuple[Template, Version]: The template (new or existing) and the newly created version.
        """
        template = Template.objects.filter(
            name=payload["template_name"], integrated_agent=integrated_agent
        ).first()

        if not template:
            template = self._create_template(
                name=payload["template_name"],
                start_condition=payload["start_condition"],
            )

        version = self._create_version(
            template=template,
            app_uuid=payload["app_uuid"],
            project_uuid=payload["project_uuid"],
        )

        return template, version
