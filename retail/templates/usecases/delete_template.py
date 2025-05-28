from rest_framework.exceptions import NotFound

from uuid import UUID

from retail.templates.models import Template


class DeleteTemplateUseCase:
    def _get_template(self, template_uuid: UUID) -> Template:
        try:
            return Template.objects.get(uuid=template_uuid, is_active=True)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {template_uuid}")

    def execute(self, template_uuid: UUID) -> None:
        template = self._get_template(template_uuid)
        template.is_active = False
        template.save()
