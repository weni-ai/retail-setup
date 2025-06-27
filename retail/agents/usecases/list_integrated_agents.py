from uuid import UUID

from django.db.models import QuerySet, Prefetch

from retail.agents.models import IntegratedAgent
from retail.templates.models import Template


class ListIntegratedAgentUseCase:
    def _get_queryset(self, project_uuid: UUID) -> QuerySet[IntegratedAgent]:
        templates_prefetch = Prefetch(
            "templates", queryset=Template.objects.filter(is_active=True)
        )

        return IntegratedAgent.objects.filter(
            project__uuid=project_uuid, is_active=True
        ).prefetch_related(templates_prefetch)

    def execute(self, project_uuid: UUID) -> QuerySet[IntegratedAgent]:
        return self._get_queryset(project_uuid)
