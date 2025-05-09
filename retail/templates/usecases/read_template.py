from rest_framework.exceptions import NotFound

from uuid import UUID

from retail.templates.models import Template


class ReadTemplateUseCase:
    def execute(self, uuid: UUID) -> Template:
        try:
            return Template.objects.get(uuid=uuid)
        except Template.DoesNotExist:
            raise NotFound()
