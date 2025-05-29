from rest_framework.exceptions import NotFound

from uuid import UUID

from retail.templates.models import Template


class ReadTemplateUseCase:
    def execute(self, uuid: UUID) -> Template:
        try:
            return Template.objects.get(uuid=uuid, is_active=True)
        except Template.DoesNotExist:
            raise NotFound(f"Template not found: {uuid}")
