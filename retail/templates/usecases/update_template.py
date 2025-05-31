from typing import Literal, TypedDict

from rest_framework.exceptions import NotFound

from retail.templates.models import Version, Template


class UpdateTemplateData(TypedDict):
    status: Literal[
        "APPROVED",
        "IN_APPEAL",
        "PENDING",
        "REJECTED",
        "PENDING_DELETION",
        "DELETED",
        "DISABLED",
        "LOCKED",
    ]
    version_uuid: str


class UpdateTemplateUseCase:
    def _get_version(self, version_uuid: str) -> Version:
        try:
            return Version.objects.get(uuid=version_uuid)
        except Version.DoesNotExist:
            raise NotFound(f"Template version not found: {version_uuid}")

    def _update_template_current_version(
        self, version: Version, template: Template
    ) -> Template:
        template.current_version = version
        template.save(update_fields=["current_version"])
        return template

    def _remove_template_from_ignore_templates(self, template: Template) -> None:
        integrated_agent = template.integrated_agent
        slug = template.parent.slug

        if slug in integrated_agent.ignore_templates:
            integrated_agent.ignore_templates.remove(slug)
            integrated_agent.save(update_fields=["ignore_templates"])

    def execute(self, payload: UpdateTemplateData) -> Template:
        version = self._get_version(payload.get("version_uuid"))
        template = version.template

        status = payload.get("status")

        if status == "APPROVED":
            template = self._update_template_current_version(version, template)
            self._remove_template_from_ignore_templates(template)

        version.status = status
        version.save(update_fields=["status"])
        return version.template
