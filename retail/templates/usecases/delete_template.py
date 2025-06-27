from django.utils import timezone

from rest_framework.exceptions import NotFound

from uuid import UUID

from retail.templates.models import Template


class DeleteTemplateUseCase:
    def _get_template(self, template_uuid: UUID) -> Template:
        try:
            return Template.objects.get(uuid=template_uuid, is_active=True)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {template_uuid}")

    def _add_template_to_ignore_list(self, template: Template) -> None:
        integrated_agent = template.integrated_agent
        integrated_agent.ignore_templates.append(template.parent.slug)
        integrated_agent.save()

    def execute(self, template_uuid: UUID) -> None:
        template = self._get_template(template_uuid)

        if not template.is_custom:
            self._add_template_to_ignore_list(template)

        template.is_active = False
        template.deleted_at = timezone.now()
        template.save()
