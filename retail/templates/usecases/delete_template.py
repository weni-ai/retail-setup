from rest_framework.exceptions import NotFound

from uuid import UUID

from retail.templates.models import Template


class DeleteTemplateUseCase:
    def get_template(self, template_uuid: UUID) -> Template:
        try:
            return Template.objects.get(uuid=template_uuid, is_active=True)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {template_uuid}")

    def _add_template_to_ignore_list(self, template: Template) -> None:
        integrated_agent = template.integrated_agent
        integrated_agent.ignore_templates.append(template.parent.slug)
        integrated_agent.save()

    def execute(self, template: Template) -> None:
        self._add_template_to_ignore_list(template)
        template.is_active = False
        template.save()
